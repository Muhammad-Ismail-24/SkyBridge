"""QUBO and Ising Hamiltonian construction for SkyBridge.

Owner: Zaheen (quantum & optimisation lead). Contract: architecture.md §4 and §6.

Pipeline position::

    Scenario --model_inputs_from_scenario--> ModelInputs --build_qubo--> QuboSpec
             --build_hamiltonian--> HamiltonianSpec (SparsePauliOp + constant offset)

Conventions
-----------
* Logical bits are always the canonical tuple ``(x0, ..., x7)`` in the order
  ``ROLE_ORDER``. Variable ``x_i`` is mapped to Qiskit qubit ``i``.
* Qiskit is little-endian: qubit 0 is the *rightmost* character of a printed
  bitstring and the least-significant bit of a basis-state index. The helpers
  ``bits_to_index``, ``index_to_bits`` and ``qiskit_bitstring_to_bits`` are the
  only places where that conversion happens.
* The QUBO is a *minimisation* problem ``E(x) = -U(x) + penalties``; the true
  mission utility ``U(x)`` lives in Ismail's ``src/evaluate.py`` and is never
  replaced by ``-E(x)`` when judging solutions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import product
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
from qiskit.quantum_info import SparsePauliOp

#: Canonical variable order (architecture.md §4, work_division.md §2).
ROLE_ORDER: tuple[str, ...] = (
    "A_H",
    "A_N",
    "B_V",
    "B_Delivery",
    "C_V",
    "C_E",
    "D_Delivery",
    "D_S",
)

#: Default extra margin added on top of the derived penalty bound.
DEFAULT_PENALTY_MARGIN = 1.0


# ---------------------------------------------------------------------------
# Bit-ordering helpers (the single source of truth for endianness)
# ---------------------------------------------------------------------------


def bits_to_index(bits: Sequence[int]) -> int:
    """Logical bits ``(x0..x{n-1})`` -> Qiskit basis-state index (x_i is qubit i)."""
    return sum(int(b) << i for i, b in enumerate(bits))


def index_to_bits(index: int, n: int) -> tuple[int, ...]:
    """Qiskit basis-state index -> logical bits ``(x0..x{n-1})``."""
    return tuple((index >> i) & 1 for i in range(n))


def qiskit_bitstring_to_bits(bitstring: str) -> tuple[int, ...]:
    """Printed Qiskit measurement string -> logical bits.

    Qiskit prints qubit 0 as the rightmost character, so the string is reversed.
    Example: ``"00000001"`` means only qubit 0 (``x0``) is 1.
    """
    s = bitstring.replace(" ", "")
    if not s or any(c not in "01" for c in s):
        raise ValueError(f"not a binary measurement string: {bitstring!r}")
    return tuple(int(c) for c in reversed(s))


def bits_to_qiskit_bitstring(bits: Sequence[int]) -> str:
    """Logical bits -> the string Qiskit would print for that basis state."""
    return "".join(str(int(b)) for b in reversed(tuple(bits)))


def all_bitstrings(n: int) -> Iterable[tuple[int, ...]]:
    """All 2**n logical assignments in lexicographic order of ``(x0..x{n-1})``."""
    return product((0, 1), repeat=n)


# ---------------------------------------------------------------------------
# Scenario -> model inputs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelInputs:
    """Normalised, solver-facing view of a ``Scenario``.

    Everything the QUBO needs and nothing else; built from scenario data so the
    QUBO never hard-codes the base instance.
    """

    n: int
    labels: tuple[str, ...]
    drones: tuple[str, ...]
    utility: tuple[float, ...]  # v_i
    energy: tuple[float, ...]  # e_i
    alpha: float
    relay_reward: float  # W
    conflict_pairs: tuple[tuple[int, int], ...]
    reward_pairs: tuple[tuple[int, int, float], ...]  # (i, j, W_ij): +W_ij * x_i x_j in U
    forbidden: tuple[int, ...]
    forbidden_reasons: Mapping[int, str]

    @property
    def net_coefficients(self) -> tuple[float, ...]:
        """Linear utility coefficients ``c_i = v_i - alpha * e_i``."""
        return tuple(v - self.alpha * e for v, e in zip(self.utility, self.energy))


def _first_attr(obj: Any, names: Sequence[str], default: Any = ...) -> Any:
    for name in names:
        if isinstance(obj, Mapping) and name in obj:
            return obj[name]
        if hasattr(obj, name):
            return getattr(obj, name)
    if default is ...:
        raise AttributeError(f"scenario is missing one of the fields {list(names)}")
    return default


def _norm_pair(i: int, j: int) -> tuple[int, int]:
    i, j = int(i), int(j)
    if i == j:
        raise ValueError(f"pair ({i}, {j}) must involve two different variables")
    return (i, j) if i < j else (j, i)


def model_inputs_from_scenario(scenario: Any) -> ModelInputs:
    """Read the documented ``Scenario`` fields (G0 contract) into ``ModelInputs``.

    Required scenario fields (attribute or mapping key):

    * ``roles``: sequence in canonical order; each role has ``drone``,
      ``utility`` (v_i) and ``energy`` (e_i), and optionally ``key``.
    * ``battery``: mapping drone -> budget; ``reserve``: return reserve.
    * ``alpha``: energy-cost multiplier; ``relay_reward``: W.
    * ``conflict_pairs``: all pairwise exclusions (same-drone, valley slot,
      payload). If absent, same-drone pairs are derived and ``exclusive_pairs``
      (if present) are appended.
    * ``relay_pairs``: (hill_index, valley_index) pairs whose relay path is
      validated in the adjacency matrix (``connected_T = Σ x_h x_v`` over them).
    * ``disabled_drones``: drones that may take no role (failure mask).

    This is the only function that depends on Ismail's ``Scenario`` layout.
    """
    roles = list(_first_attr(scenario, ["roles"]))
    n = len(roles)
    if n == 0:
        raise ValueError("scenario has no roles")

    def role_field(role: Any, names: Sequence[str], default: Any = ...) -> Any:
        return _first_attr(role, names, default)

    labels = tuple(
        str(role_field(r, ["key", "label", "name"], ROLE_ORDER[i] if i < len(ROLE_ORDER) else f"x{i}"))
        for i, r in enumerate(roles)
    )
    drones = tuple(str(role_field(r, ["drone", "drone_id"])) for r in roles)
    utility = tuple(float(role_field(r, ["utility", "value", "v"])) for r in roles)
    energy = tuple(float(role_field(r, ["energy", "energy_cost", "cost", "e"])) for r in roles)

    battery = dict(_first_attr(scenario, ["battery", "battery_budgets"]))
    reserve = float(_first_attr(scenario, ["reserve", "battery_reserve"]))
    alpha = float(_first_attr(scenario, ["alpha"]))
    relay_reward = float(_first_attr(scenario, ["relay_reward", "W", "connectivity_weight"]))
    disabled = {str(d) for d in _first_attr(scenario, ["disabled_drones", "failed_drones"], ())}

    explicit_pairs = _first_attr(scenario, ["conflict_pairs"], None)
    if explicit_pairs is not None:
        conflicts = {_norm_pair(i, j) for i, j in explicit_pairs}
    else:
        conflicts = {
            (i, j) for i in range(n) for j in range(i + 1, n) if drones[i] == drones[j]
        }
        conflicts |= {_norm_pair(i, j) for i, j in _first_attr(scenario, ["exclusive_pairs"], ())}

    reward_pairs = tuple(
        (*_norm_pair(h, v), relay_reward) for h, v in _first_attr(scenario, ["relay_pairs"])
    )

    forbidden_reasons: dict[int, str] = {}
    for i in range(n):
        if drones[i] in disabled:
            forbidden_reasons[i] = f"drone {drones[i]} disabled"
        elif drones[i] not in battery:
            raise ValueError(f"no battery budget for drone {drones[i]!r}")
        elif energy[i] + reserve > battery[drones[i]]:
            forbidden_reasons[i] = (
                f"energy {energy[i]:g} + reserve {reserve:g} > battery {battery[drones[i]]:g}"
            )

    for i, j in conflicts:
        if not (0 <= i < n and 0 <= j < n):
            raise ValueError(f"conflict pair ({i}, {j}) out of range for {n} variables")

    return ModelInputs(
        n=n,
        labels=labels,
        drones=drones,
        utility=utility,
        energy=energy,
        alpha=alpha,
        relay_reward=relay_reward,
        conflict_pairs=tuple(sorted(conflicts)),
        reward_pairs=tuple(sorted(reward_pairs)),
        forbidden=tuple(sorted(forbidden_reasons)),
        forbidden_reasons=forbidden_reasons,
    )


# ---------------------------------------------------------------------------
# QUBO
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class QuboSpec:
    """Minimisation QUBO ``E(x) = offset + Σ linear_i x_i + Σ_{i<j} quadratic_ij x_i x_j``."""

    n: int
    ordering: tuple[str, ...]
    linear: tuple[float, ...]
    quadratic: Mapping[tuple[int, int], float]  # keys (i, j) with i < j, duplicates merged
    offset: float
    penalty: float
    penalty_bound: float
    penalty_derivation: str
    weights: Mapping[str, float]
    inputs: ModelInputs = field(repr=False)

    def energy(self, bits: Sequence[int]) -> float:
        return qubo_energy(self, bits)

    def matrix(self) -> np.ndarray:
        """Upper-triangular Q with linear terms on the diagonal (offset excluded)."""
        q = np.zeros((self.n, self.n))
        np.fill_diagonal(q, self.linear)
        for (i, j), b in self.quadratic.items():
            q[i, j] = b
        return q

    def to_dict(self) -> dict:
        return {
            "n_binary": self.n,
            "role_order": list(self.ordering),
            "linear": list(self.linear),
            "quadratic": [[i, j, b] for (i, j), b in sorted(self.quadratic.items())],
            "offset": self.offset,
            "penalty": self.penalty,
            "penalty_bound": self.penalty_bound,
            "penalty_derivation": self.penalty_derivation,
            "weights": dict(self.weights),
            "conflict_pairs": [list(p) for p in self.inputs.conflict_pairs],
            "reward_pairs": [list(p) for p in self.inputs.reward_pairs],
            "forbidden": {self.ordering[i]: r for i, r in self.inputs.forbidden_reasons.items()},
        }


def penalty_lower_bound(inputs: ModelInputs) -> tuple[float, str]:
    """Smallest P for which the single-flip argument guarantees a feasible ground state.

    Take any infeasible x and a variable ``i`` with ``x_i = 1`` that is in a violated
    conflict pair or is forbidden. Setting ``x_i = 0`` changes ``E`` by

        ΔE = c_i + Σ_j W_ij x_j - P·k_i,   k_i >= 1 violations removed,

    because ``E`` contains ``-c_i x_i - Σ_j W_ij x_i x_j + P·(violations)``.
    Hence ``ΔE < 0`` whenever ``P > B := max_i (max(c_i, 0) + Σ_j max(W_ij, 0))``.
    Repeating the flip strictly lowers ``E`` until x is feasible, so every
    infeasible state has a feasible state of strictly lower energy, i.e. the QUBO
    ground state is a feasible assignment and its energy equals ``-U_max``.
    """
    c = inputs.net_coefficients
    reward_touch = [0.0] * inputs.n
    for i, j, w in inputs.reward_pairs:
        reward_touch[i] += max(w, 0.0)
        reward_touch[j] += max(w, 0.0)
    per_var = [max(c[i], 0.0) + reward_touch[i] for i in range(inputs.n)]
    bound = max(per_var)
    worst = int(np.argmax(per_var))
    text = (
        "single-flip bound B = max_i(max(c_i,0) + sum_j W_ij); "
        f"B = {bound:g} attained at {inputs.labels[worst]}; P = B + margin guarantees "
        "every infeasible state has a strictly lower-energy feasible neighbour"
    )
    return bound, text


def build_qubo(
    scenario: Any,
    *,
    penalty: float | None = None,
    penalty_margin: float = DEFAULT_PENALTY_MARGIN,
) -> QuboSpec:
    """Build the penalty-augmented minimisation QUBO from scenario data.

    ``E(x) = -Σ_i c_i x_i - Σ_(i,j) W_ij x_i x_j + P Σ_conflict x_i x_j + P Σ_forbidden x_i``
    with ``c_i = v_i - alpha e_i``. ``penalty`` defaults to the derived bound plus
    ``penalty_margin``; an explicit value below the bound is rejected.
    """
    inputs = scenario if isinstance(scenario, ModelInputs) else model_inputs_from_scenario(scenario)
    bound, derivation = penalty_lower_bound(inputs)
    if penalty is None:
        if penalty_margin <= 0:
            raise ValueError("penalty_margin must be positive (the bound is strict)")
        p = bound + penalty_margin
    else:
        p = float(penalty)
        if p <= bound:
            raise ValueError(f"penalty {p} does not exceed the feasibility bound {bound}")

    linear = [-c for c in inputs.net_coefficients]
    for i in inputs.forbidden:
        linear[i] += p

    quadratic: dict[tuple[int, int], float] = {}
    for i, j, w in inputs.reward_pairs:
        quadratic[(i, j)] = quadratic.get((i, j), 0.0) - w
    for i, j in inputs.conflict_pairs:
        quadratic[(i, j)] = quadratic.get((i, j), 0.0) + p
    quadratic = {k: v for k, v in quadratic.items() if v != 0.0}

    return QuboSpec(
        n=inputs.n,
        ordering=inputs.labels,
        linear=tuple(linear),
        quadratic=quadratic,
        offset=0.0,
        penalty=p,
        penalty_bound=bound,
        penalty_derivation=derivation,
        weights={"alpha": inputs.alpha, "relay_reward_W": inputs.relay_reward},
        inputs=inputs,
    )


def qubo_energy(qubo: QuboSpec, bits: Sequence[int]) -> float:
    """Direct evaluation of the QUBO polynomial (used to verify the Hamiltonian)."""
    if len(bits) != qubo.n:
        raise ValueError(f"expected {qubo.n} bits, got {len(bits)}")
    x = [int(b) for b in bits]
    e = qubo.offset + sum(a * xi for a, xi in zip(qubo.linear, x))
    e += sum(b * x[i] * x[j] for (i, j), b in qubo.quadratic.items())
    return float(e)


def qubo_unpenalised_objective(qubo: QuboSpec, bits: Sequence[int]) -> float:
    """``U(x)`` as encoded inside the QUBO (no penalties). Diagnostic only."""
    inp = qubo.inputs
    u = sum(c * int(b) for c, b in zip(inp.net_coefficients, bits))
    u += sum(w * int(bits[i]) * int(bits[j]) for i, j, w in inp.reward_pairs)
    return float(u)


def qubo_violations(qubo: QuboSpec, bits: Sequence[int]) -> list[str]:
    """Penalty terms switched on by ``bits`` (diagnostic, not the feasibility oracle)."""
    inp = qubo.inputs
    out = [
        f"conflict {inp.labels[i]}+{inp.labels[j]}"
        for i, j in inp.conflict_pairs
        if bits[i] and bits[j]
    ]
    out += [f"forbidden {inp.labels[i]} ({inp.forbidden_reasons[i]})" for i in inp.forbidden if bits[i]]
    return out


# ---------------------------------------------------------------------------
# Ising Hamiltonian
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HamiltonianSpec:
    """Ising form ``E(x) = offset + <z| operator |z>`` with ``x_i = (1 - z_i)/2``.

    ``operator`` has no identity term; the constant lives in ``offset``.
    Variable ``x_i`` is qubit ``i`` (Qiskit little-endian).
    """

    operator: SparsePauliOp
    offset: float
    n: int
    ordering: tuple[str, ...]
    h: tuple[float, ...]  # coefficients of Z_i
    J: Mapping[tuple[int, int], float]  # coefficients of Z_i Z_j

    def diagonal(self) -> np.ndarray:
        """Exact diagonal of ``operator`` (index = Qiskit basis state), computed by Qiskit."""
        return np.real(self.operator.to_matrix(sparse=True).diagonal())

    def energy(self, bits: Sequence[int]) -> float:
        return ising_energy(self, bits)

    def max_abs_coefficient(self) -> float:
        return float(np.max(np.abs(self.operator.coeffs))) if len(self.operator) else 0.0

    def to_dict(self) -> dict:
        return {
            "offset": self.offset,
            "num_qubits": self.n,
            "terms": [[label, float(np.real(c))] for label, c in self.operator.to_list()],
            "qubit_for_variable": {name: i for i, name in enumerate(self.ordering)},
            "bitstring_convention": "Qiskit little-endian: printed string reversed gives (x0..x7)",
        }


def build_hamiltonian(qubo: QuboSpec) -> HamiltonianSpec:
    """Map the QUBO to an Ising cost operator via ``x_i = (I - Z_i)/2``.

    ``a_i x_i = a_i/2 - (a_i/2) Z_i`` and
    ``b_ij x_i x_j = b_ij/4 (I - Z_i - Z_j + Z_i Z_j)``, hence

    * ``offset = offset_Q + Σ a_i/2 + Σ b_ij/4``
    * ``h_i = -a_i/2 - Σ_{j} b_ij/4`` (sum over pairs containing i)
    * ``J_ij = b_ij/4``
    """
    n = qubo.n
    offset = qubo.offset + sum(qubo.linear) / 2.0 + sum(qubo.quadratic.values()) / 4.0
    h = [-a / 2.0 for a in qubo.linear]
    J: dict[tuple[int, int], float] = {}
    for (i, j), b in qubo.quadratic.items():
        h[i] -= b / 4.0
        h[j] -= b / 4.0
        J[(i, j)] = J.get((i, j), 0.0) + b / 4.0

    terms = [("Z", [i], h[i]) for i in range(n) if h[i] != 0.0]
    terms += [("ZZ", [i, j], v) for (i, j), v in sorted(J.items()) if v != 0.0]
    if terms:
        op = SparsePauliOp.from_sparse_list(terms, num_qubits=n).simplify(atol=0.0)
    else:
        op = SparsePauliOp("I" * n, coeffs=[0.0])
    return HamiltonianSpec(
        operator=op, offset=float(offset), n=n, ordering=qubo.ordering, h=tuple(h), J=J
    )


def ising_energy(ham: HamiltonianSpec, bits: Sequence[int]) -> float:
    """``offset + <z|H|z>`` evaluated from the Pauli labels of the built operator.

    Independent of ``build_hamiltonian``'s algebra: it reads the SparsePauliOp
    terms and uses ``Z|0> = +|0>``, ``Z|1> = -|1>``.
    """
    if len(bits) != ham.n:
        raise ValueError(f"expected {ham.n} bits, got {len(bits)}")
    z = [1 - 2 * int(b) for b in bits]  # eigenvalue of Z_i
    total = ham.offset
    for label, coeff in ham.operator.to_list():
        # label[k] acts on qubit n-1-k (Qiskit little-endian)
        sign = 1
        for k, ch in enumerate(label):
            if ch == "Z":
                sign *= z[ham.n - 1 - k]
            elif ch != "I":
                raise ValueError(f"non-diagonal Pauli term {label}")
        total += float(np.real(coeff)) * sign
    return float(total)


def energy_table(qubo: QuboSpec, ham: HamiltonianSpec | None = None) -> dict:
    """Compare QUBO and Ising energies for all 2**n states; returns max error and arrays."""
    ham = ham or build_hamiltonian(qubo)
    diag = ham.diagonal()
    q, ising_terms, ising_diag = [], [], []
    for bits in all_bitstrings(qubo.n):
        q.append(qubo_energy(qubo, bits))
        ising_terms.append(ising_energy(ham, bits))
        ising_diag.append(float(diag[bits_to_index(bits)]) + ham.offset)
    q_arr, t_arr, d_arr = map(np.asarray, (q, ising_terms, ising_diag))
    return {
        "states": 2**qubo.n,
        "max_abs_error_terms": float(np.max(np.abs(q_arr - t_arr))),
        "max_abs_error_matrix_diagonal": float(np.max(np.abs(q_arr - d_arr))),
        "qubo": q_arr,
    }
