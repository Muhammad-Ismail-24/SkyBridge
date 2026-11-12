"""Qiskit QAOA solver for the SkyBridge QUBO.

Owner: Zaheen. Contract: architecture.md §5-§6, work_division.md Z2.

What actually runs
------------------
1. ``build_hamiltonian`` turns the QUBO into an Ising ``SparsePauliOp`` H_C.
2. ``qiskit.circuit.library.qaoa_ansatz`` builds |γ,β> = Π_k e^{-iβ_k H_M} e^{-iγ_k H_C} |+>^n
   with the transverse-field mixer H_M = Σ X_i.
3. A classical outer loop (SciPy COBYLA) minimises <γ,β|H_C|γ,β>, evaluated by
   ``qiskit.primitives.StatevectorEstimator`` on the real circuit.
   A coarse p=1 (γ, β) grid scan picks the first COBYLA start point; for p>1
   each depth is warm-started from the previous optimum (INTERP). Those
   evaluations are counted and reported separately as warm-start evaluations.
4. The optimised circuit is measured with ``StatevectorSampler`` (seeded, finite
   shots). Measured bitstrings are decoded to logical bits (little-endian
   reversal) and returned with their counts.

Feasibility and true utility are *not* judged here from QUBO energy:
``select_feasible`` re-checks every sampled assignment with Ismail's original
``is_feasible``/``score_feasible``. The exact solver is never consulted.
"""

from __future__ import annotations

import platform
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy.optimize import minimize

import qiskit
from qiskit import transpile
from qiskit.circuit import QuantumCircuit
from qiskit.circuit.library import qaoa_ansatz
from qiskit.primitives import StatevectorEstimator, StatevectorSampler

from src.baseline import FeasibleFn, ScoreFn, resolve_evaluator, total_utility
from src.model import (
    HamiltonianSpec,
    QuboSpec,
    build_hamiltonian,
    qiskit_bitstring_to_bits,
    qubo_energy,
)

SAMPLER_NAME = "qiskit.primitives.StatevectorSampler"
ESTIMATOR_NAME = "qiskit.primitives.StatevectorEstimator"
GRID_POINTS = 12  # per axis, p=1 warm start only


@dataclass(frozen=True)
class Sample:
    bits: tuple[int, ...]
    bitstring_qiskit: str
    count: int
    probability: float  # empirical, count / shots
    qubo_energy: float


@dataclass(frozen=True)
class QuantumResult:
    ran_qiskit: bool
    backend: str
    n_qubits: int
    reps: int
    shots: int
    seed: int
    maxiter: int
    hamiltonian_scale: float
    initial_params: dict[str, float]
    optimal_params: dict[str, float]
    optimal_expectation: float  # <H_C> + offset, i.e. expected QUBO energy
    warm_start_evaluations: int
    optimizer_evaluations: int
    optimizer_success: bool
    optimizer_message: str
    expectation_trace: tuple[float, ...] = field(repr=False)
    circuit_depth: int = 0
    circuit_two_qubit_gates: int = 0
    circuit_ops: dict[str, int] = field(default_factory=dict)
    samples: tuple[Sample, ...] = field(repr=False, default=())
    elapsed_seconds: float = 0.0
    software_versions: dict[str, str] = field(default_factory=dict)

    @property
    def counts(self) -> dict[str, int]:
        """Raw Qiskit-ordered counts as measured."""
        return {s.bitstring_qiskit: s.count for s in self.samples}

    @property
    def most_frequent(self) -> Sample | None:
        return self.samples[0] if self.samples else None

    @property
    def lowest_energy_sample(self) -> Sample | None:
        return min(self.samples, key=lambda s: (s.qubo_energy, s.bits)) if self.samples else None

    def to_dict(self, include_samples: bool = True) -> dict:
        d = {
            "ran_qiskit": self.ran_qiskit,
            "backend": self.backend,
            "expectation_primitive": ESTIMATOR_NAME,
            "n_qubits": self.n_qubits,
            "qaoa_reps": self.reps,
            "shots": self.shots,
            "seed": self.seed,
            "maxiter": self.maxiter,
            "hamiltonian_scale": self.hamiltonian_scale,
            "initial_params": self.initial_params,
            "optimal_params": self.optimal_params,
            "optimal_expectation_qubo_energy": self.optimal_expectation,
            "warm_start_evaluations": self.warm_start_evaluations,
            "optimizer": "scipy.optimize.minimize(method='COBYLA')",
            "optimizer_iterations": self.optimizer_evaluations,
            "optimizer_success": self.optimizer_success,
            "optimizer_message": self.optimizer_message,
            "circuit_depth": self.circuit_depth,
            "circuit_two_qubit_gates": self.circuit_two_qubit_gates,
            "circuit_ops": self.circuit_ops,
            "distinct_bitstrings_sampled": len(self.samples),
            "elapsed_seconds": self.elapsed_seconds,
            "software_versions": self.software_versions,
        }
        if include_samples:
            d["samples"] = [
                {
                    "bits": list(s.bits),
                    "qiskit_bitstring": s.bitstring_qiskit,
                    "count": s.count,
                    "probability": s.probability,
                    "qubo_energy": s.qubo_energy,
                }
                for s in self.samples
            ]
        return d


def software_versions() -> dict[str, str]:
    import scipy

    return {
        "python": platform.python_version(),
        "qiskit": qiskit.__version__,
        "numpy": np.__version__,
        "scipy": scipy.__version__,
    }


def build_qaoa_circuit(ham: HamiltonianSpec, reps: int, scale: float = 1.0) -> QuantumCircuit:
    """Parameterised QAOA ansatz for ``H_C / scale`` (scale only reparameterises γ)."""
    if reps < 1:
        raise ValueError("reps must be >= 1")
    return qaoa_ansatz(ham.operator / scale, reps=reps)


def _param_order(circuit: QuantumCircuit) -> tuple[list, list]:
    betas = sorted((p for p in circuit.parameters if p.name.startswith("β")), key=lambda p: p.index)
    gammas = sorted((p for p in circuit.parameters if p.name.startswith("γ")), key=lambda p: p.index)
    return gammas, betas


def _interp(angles: np.ndarray) -> np.ndarray:
    """INTERP: depth-p angles -> depth-(p+1) start, with zero padding at both ends."""
    p = len(angles)
    padded = np.concatenate([[0.0], angles, [0.0]])
    return np.array(
        [((i - 1) / p) * padded[i - 1] + ((p - i + 1) / p) * padded[i] for i in range(1, p + 2)]
    )


def solve_qaoa(
    qubo: QuboSpec,
    *,
    seed: int,
    shots: int,
    reps: int,
    maxiter: int,
) -> QuantumResult:
    """Optimise and sample a real QAOA circuit for ``qubo`` on the local simulator."""
    if shots < 1 or maxiter < 1:
        raise ValueError("shots and maxiter must be positive")
    t0 = time.perf_counter()
    ham = build_hamiltonian(qubo)
    # Normalising H_C by its largest coefficient keeps γ in an O(1) range for any
    # penalty size; it changes the γ scale only, not the state family or ground state.
    scale = ham.max_abs_coefficient() or 1.0
    circuits = {d: build_qaoa_circuit(ham, d, scale) for d in range(1, reps + 1)}
    ansatz = circuits[reps]
    gammas, betas = _param_order(ansatz)
    ordered = list(ansatz.parameters)  # Qiskit's canonical binding order

    estimator = StatevectorEstimator(seed=seed)
    trace: list[float] = []

    def bind(circ: QuantumCircuit, gamma_vec, beta_vec) -> list[float]:
        g_par, b_par = _param_order(circ)
        values = {g: float(v) for g, v in zip(g_par, gamma_vec)}
        values.update({b: float(v) for b, v in zip(b_par, beta_vec)})
        return [values[p] for p in circ.parameters]

    def expectation(gamma_vec: np.ndarray, beta_vec: np.ndarray) -> float:
        circ = circuits[len(gamma_vec)]
        bound = bind(circ, gamma_vec, beta_vec)
        ev = estimator.run([(circ, ham.operator, bound)]).result()[0].data.evs
        return float(np.real(ev)) + ham.offset

    # ---- warm start: p=1 grid scan ----------------------------------------
    warm_evals = 0
    best = (np.inf, 0.0, 0.0)
    for g in np.linspace(-np.pi, np.pi, GRID_POINTS, endpoint=False):
        for b in np.linspace(-np.pi / 2, np.pi / 2, GRID_POINTS, endpoint=False):
            val = expectation(np.array([g]), np.array([b]))
            warm_evals += 1
            if val < best[0]:
                best = (val, g, b)
    theta_p = np.array([best[1], best[2]])

    def run_cobyla(depth: int, start: np.ndarray):
        def obj(theta: np.ndarray) -> float:
            val = expectation(theta[:depth], theta[depth:])
            trace.append(val)
            return val

        return minimize(obj, start, method="COBYLA", options={"maxiter": int(maxiter), "rhobeg": 0.3})

    # ---- layer-wise INTERP schedule for reps > 1 (Zhou et al., PRX 10, 021067):
    # optimise depth d, interpolate its optimum to depth d+1 as the next start.
    # Evaluations at depths < reps are counted as warm-start evaluations.
    for depth in range(1, reps + 1):
        if depth > 1:
            theta_p = np.concatenate(
                [_interp(theta_p[: depth - 1]), _interp(theta_p[depth - 1 :])]
            )
        theta0 = theta_p.copy()  # start point of the final reported optimisation
        res = run_cobyla(depth, theta_p)
        theta_p = np.asarray(res.x, dtype=float)
        if depth < reps:
            warm_evals += int(res.nfev)
    theta = theta_p

    # ---- sample the optimised circuit -------------------------------------
    measured = ansatz.copy()
    measured.measure_all()
    values = {g: float(v) for g, v in zip(gammas, theta[:reps])}
    values.update({b: float(v) for b, v in zip(betas, theta[reps:])})
    sampler = StatevectorSampler(seed=seed)
    job = sampler.run([(measured, [values[p] for p in ordered])], shots=int(shots))
    counts = job.result()[0].data.meas.get_counts()

    samples = []
    for bitstring, count in counts.items():
        bits = qiskit_bitstring_to_bits(bitstring)
        samples.append(
            Sample(
                bits=bits,
                bitstring_qiskit=bitstring,
                count=int(count),
                probability=count / shots,
                qubo_energy=qubo_energy(qubo, bits),
            )
        )
    samples.sort(key=lambda s: (-s.count, s.bits))

    compiled = transpile(
        measured.assign_parameters([values[p] for p in ordered]),
        basis_gates=["rz", "sx", "x", "cx", "h", "rx", "measure"],
        optimization_level=1,
        seed_transpiler=seed,
    )
    ops = {k: int(v) for k, v in compiled.count_ops().items()}

    return QuantumResult(
        ran_qiskit=True,
        backend=SAMPLER_NAME,
        n_qubits=ansatz.num_qubits,
        reps=reps,
        shots=int(shots),
        seed=int(seed),
        maxiter=int(maxiter),
        hamiltonian_scale=float(scale),
        initial_params={
            **{f"gamma_{i}": float(theta0[i]) for i in range(reps)},
            **{f"beta_{i}": float(theta0[reps + i]) for i in range(reps)},
        },
        optimal_params={
            **{f"gamma_{i}": float(theta[i]) for i in range(reps)},
            **{f"beta_{i}": float(theta[reps + i]) for i in range(reps)},
        },
        optimal_expectation=float(res.fun),
        warm_start_evaluations=warm_evals,
        optimizer_evaluations=int(res.nfev),
        optimizer_success=bool(res.success),
        optimizer_message=str(res.message),
        expectation_trace=tuple(trace),
        circuit_depth=int(compiled.depth()),
        circuit_two_qubit_gates=int(ops.get("cx", 0)),
        circuit_ops=ops,
        samples=tuple(samples),
        elapsed_seconds=time.perf_counter() - t0,
        software_versions=software_versions(),
    )


@dataclass(frozen=True)
class FeasibleSelection:
    status: str  # "feasible_found" | "no_feasible_sample"
    best_bits: tuple[int, ...] | None
    utility: float | None
    breakdown: dict | None
    best_sample_count: int | None
    feasible_sample_fraction: float  # feasible shots / total shots
    feasible_distinct: int
    infeasible_distinct: int
    lowest_energy_sample_bits: tuple[int, ...] | None
    lowest_energy_sample_feasible: bool | None
    most_frequent_bits: tuple[int, ...] | None
    most_frequent_feasible: bool | None
    selection_rule: str = (
        "highest true utility among sampled assignments that pass the original "
        "is_feasible; ties -> higher count, then smallest canonical tuple"
    )

    def to_dict(self) -> dict:
        def lst(b):
            return list(b) if b is not None else None

        return {
            "status": self.status,
            "best_feasible_bits": lst(self.best_bits),
            "utility": self.utility,
            "breakdown": self.breakdown,
            "best_sample_count": self.best_sample_count,
            "feasible_sample_fraction": self.feasible_sample_fraction,
            "feasible_distinct_bitstrings": self.feasible_distinct,
            "infeasible_distinct_bitstrings": self.infeasible_distinct,
            "lowest_energy_sample_bits": lst(self.lowest_energy_sample_bits),
            "lowest_energy_sample_feasible": self.lowest_energy_sample_feasible,
            "most_frequent_bits": lst(self.most_frequent_bits),
            "most_frequent_feasible": self.most_frequent_feasible,
            "selection_rule": self.selection_rule,
        }


def select_feasible(
    result: QuantumResult,
    scenario: Any,
    *,
    is_feasible: FeasibleFn | None = None,
    score_feasible: ScoreFn | None = None,
) -> FeasibleSelection:
    """Pick the best *feasible sampled* assignment using the original evaluator.

    Infeasible samples are rejected, never repaired. If none is feasible the
    status is ``no_feasible_sample`` and no assignment is returned.
    """
    feasible_fn, score_fn = resolve_evaluator(is_feasible, score_feasible)
    feasible: list[tuple[Sample, float, dict]] = []
    feasible_shots = 0
    flags: dict[tuple[int, ...], bool] = {}
    for s in result.samples:
        ok = bool(feasible_fn(s.bits, scenario))
        flags[s.bits] = ok
        if ok:
            bd = score_fn(s.bits, scenario)
            feasible.append((s, total_utility(bd), bd))
            feasible_shots += s.count

    low = result.lowest_energy_sample
    top = result.most_frequent
    common = dict(
        feasible_sample_fraction=feasible_shots / result.shots if result.shots else 0.0,
        feasible_distinct=len(feasible),
        infeasible_distinct=len(result.samples) - len(feasible),
        lowest_energy_sample_bits=low.bits if low else None,
        lowest_energy_sample_feasible=flags.get(low.bits) if low else None,
        most_frequent_bits=top.bits if top else None,
        most_frequent_feasible=flags.get(top.bits) if top else None,
    )
    if not feasible:
        return FeasibleSelection(
            status="no_feasible_sample",
            best_bits=None,
            utility=None,
            breakdown=None,
            best_sample_count=None,
            **common,
        )
    feasible.sort(key=lambda t: (-t[1], -t[0].count, t[0].bits))
    s, u, bd = feasible[0]
    return FeasibleSelection(
        status="feasible_found",
        best_bits=s.bits,
        utility=u,
        breakdown=bd,
        best_sample_count=s.count,
        **common,
    )


def probability_of(result: QuantumResult, bits: tuple[int, ...] | None) -> float:
    """Empirical sampled probability of a specific assignment (0 if never seen)."""
    if bits is None:
        return 0.0
    return sum(s.probability for s in result.samples if s.bits == tuple(bits))
