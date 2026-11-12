"""Tests for src/model.py (QUBO + Ising) and src/quantum.py (QAOA). Owner: Zaheen."""

from __future__ import annotations

import numpy as np
import pytest

from src import model as M
from src import quantum as Q
from tests import reference_contract as ref

TOL = 1e-8
BASE_C = (-1.0, 6.5, -0.75, 3.75, -0.5, 5.25, 4.0, 2.75)  # v_i - 0.05 e_i, hand-computed


def ref_variants():
    yield "base/balanced", ref.reference_scenario("base", "balanced")
    yield "base/mission_first", ref.reference_scenario("base", "mission_first")
    yield "base/coverage_first", ref.reference_scenario("base", "coverage_first")
    yield "relay_failure", ref.reference_scenario("relay_failure", "balanced")
    yield "shadow_block_B", ref.reference_scenario(blocked_edges={("B_V", "Team")})
    yield "low_battery_D", ref.reference_scenario(battery={**ref.BATTERY, "D": 50.0})


VARIANTS = list(ref_variants())


# ---------------------------------------------------------------------------
# Bit ordering
# ---------------------------------------------------------------------------


def test_role_order_is_canonical():
    assert M.ROLE_ORDER == ("A_H", "A_N", "B_V", "B_Delivery", "C_V", "C_E", "D_Delivery", "D_S")


def test_only_x0_and_only_x7_endianness():
    only_x0 = (1, 0, 0, 0, 0, 0, 0, 0)
    only_x7 = (0, 0, 0, 0, 0, 0, 0, 1)
    assert M.bits_to_index(only_x0) == 1
    assert M.bits_to_index(only_x7) == 128
    assert M.bits_to_qiskit_bitstring(only_x0) == "00000001"
    assert M.bits_to_qiskit_bitstring(only_x7) == "10000000"
    assert M.qiskit_bitstring_to_bits("00000001") == only_x0
    assert M.qiskit_bitstring_to_bits("10000000") == only_x7
    for k in range(256):
        bits = M.index_to_bits(k, 8)
        assert M.bits_to_index(bits) == k
        assert M.qiskit_bitstring_to_bits(format(k, "08b")) == bits


def test_qiskit_statevector_agrees_with_bit_helpers():
    """Prepare |x0=1> and |x7=1> in a real circuit and read Qiskit's own labels."""
    from qiskit import QuantumCircuit
    from qiskit.quantum_info import Statevector

    for var in (0, 7):
        qc = QuantumCircuit(8)
        qc.x(var)
        probs = Statevector(qc).probabilities_dict()
        (label,) = probs
        bits = M.qiskit_bitstring_to_bits(label)
        assert bits == tuple(int(i == var) for i in range(8))


def test_single_variable_hamiltonian_energy_matches_linear_term(base_scenario):
    qubo = M.build_qubo(base_scenario)
    ham = M.build_hamiltonian(qubo)
    for i in range(8):
        bits = tuple(int(k == i) for k in range(8))
        assert ham.energy(bits) == pytest.approx(qubo.linear[i], abs=TOL)


# ---------------------------------------------------------------------------
# QUBO coefficients and penalty
# ---------------------------------------------------------------------------


def test_base_qubo_coefficients_match_hand_derivation():
    sc = ref.reference_scenario()
    qubo = M.build_qubo(sc)
    assert qubo.ordering == M.ROLE_ORDER
    assert qubo.inputs.net_coefficients == pytest.approx(BASE_C)
    assert qubo.linear == pytest.approx(tuple(-c for c in BASE_C))  # no forbidden roles in base
    P = qubo.penalty
    expected = {(0, 2): -22.0, (0, 4): -22.0}
    for pair in [(0, 1), (2, 3), (4, 5), (6, 7), (2, 4), (3, 6)]:
        expected[pair] = P
    assert dict(qubo.quadratic) == pytest.approx(expected)
    assert qubo.offset == 0.0


def test_penalty_bound_derivation_and_value():
    qubo = M.build_qubo(ref.reference_scenario())
    # B = max_i(max(c_i,0) + Σ_j W_ij): x0 touches two reward pairs -> 0 + 2*22 = 44
    assert qubo.penalty_bound == pytest.approx(44.0)
    assert qubo.penalty == pytest.approx(45.0)
    assert qubo.penalty > qubo.penalty_bound
    assert "single-flip" in qubo.penalty_derivation
    with pytest.raises(ValueError):
        M.build_qubo(ref.reference_scenario(), penalty=44.0)
    assert M.build_qubo(ref.reference_scenario(), penalty=60.0).penalty == 60.0


def test_six_conflict_pairs_present():
    qubo = M.build_qubo(ref.reference_scenario())
    assert set(qubo.inputs.conflict_pairs) == {(0, 1), (2, 3), (4, 5), (6, 7), (2, 4), (3, 6)}


def test_failure_mask_forbids_both_b_roles():
    qubo = M.build_qubo(ref.reference_scenario("relay_failure"))
    assert qubo.inputs.forbidden == (2, 3)
    assert qubo.linear[2] == pytest.approx(0.75 + qubo.penalty)
    assert qubo.linear[3] == pytest.approx(-3.75 + qubo.penalty)


def test_battery_reserve_forbids_role():
    sc = ref.reference_scenario(battery={**ref.BATTERY, "D": 50.0})  # 40 + 15 > 50
    qubo = M.build_qubo(sc)
    assert qubo.inputs.forbidden == (6,)
    assert "reserve" in qubo.inputs.forbidden_reasons[6]


def test_blocked_link_removes_connectivity_reward():
    sc = ref.reference_scenario(blocked_edges={("B_V", "Team")})
    qubo = M.build_qubo(sc)
    assert qubo.inputs.reward_pairs == ((0, 4, 22.0),)
    assert (0, 2) not in qubo.quadratic  # no reward, and B_V/A_H share no conflict pair


def test_qubo_depends_on_scenario_data():
    a = M.build_qubo(ref.reference_scenario())
    b = M.build_qubo(ref.reference_scenario(utility_override={1: 20.0}))
    assert a.linear[1] != b.linear[1]
    assert M.build_qubo(ref.reference_scenario("base", "coverage_first")).quadratic[(0, 2)] == -35.0


# ---------------------------------------------------------------------------
# QUBO <-> Ising equivalence and feasibility of the ground state (all 256 states)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name,sc", VARIANTS, ids=[v[0] for v in VARIANTS])
def test_256_state_qubo_ising_equivalence(name, sc):
    qubo = M.build_qubo(sc)
    ham = M.build_hamiltonian(qubo)
    table = M.energy_table(qubo, ham)
    assert table["states"] == 256
    assert table["max_abs_error_terms"] < TOL
    assert table["max_abs_error_matrix_diagonal"] < TOL
    assert ham.operator.num_qubits == 8


def test_ising_offset_and_coefficients_formula():
    qubo = M.build_qubo(ref.reference_scenario())
    ham = M.build_hamiltonian(qubo)
    assert ham.offset == pytest.approx(sum(qubo.linear) / 2 + sum(qubo.quadratic.values()) / 4)
    for (i, j), b in qubo.quadratic.items():
        assert ham.J[(i, j)] == pytest.approx(b / 4)
    labels = {lab for lab, _ in ham.operator.to_list()}
    assert all(set(lab) <= {"I", "Z"} for lab in labels)
    assert "I" * 8 not in labels  # constant kept separately in offset


@pytest.mark.parametrize("name,sc", VARIANTS, ids=[v[0] for v in VARIANTS])
def test_ground_state_feasible_and_equals_true_optimum(name, sc):
    qubo = M.build_qubo(sc)
    feasible_e, infeasible_e = [], []
    for bits in M.all_bitstrings(8):
        e = qubo.energy(bits)
        if ref.ref_is_feasible(bits, sc):
            # Inside the feasible set the QUBO is exactly -U(x).
            assert -e == pytest.approx(ref.ref_score_feasible(bits, sc)["total_utility"], abs=TOL)
            feasible_e.append(e)
        else:
            infeasible_e.append(e)
    assert min(infeasible_e) > min(feasible_e)


def test_single_flip_argument_holds_for_every_infeasible_state():
    sc = ref.reference_scenario()
    qubo = M.build_qubo(sc)
    inp = qubo.inputs
    for bits in M.all_bitstrings(8):
        if ref.ref_is_feasible(bits, sc):
            continue
        violators = {i for i, j in inp.conflict_pairs if bits[i] and bits[j]}
        violators |= {j for i, j in inp.conflict_pairs if bits[i] and bits[j]}
        violators |= {i for i in inp.forbidden if bits[i]}
        assert violators
        for i in violators:
            flipped = tuple(0 if k == i else b for k, b in enumerate(bits))
            assert qubo.energy(flipped) < qubo.energy(bits)


# ---------------------------------------------------------------------------
# QAOA (real Qiskit execution)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def qaoa_run():
    sc = ref.reference_scenario()
    qubo = M.build_qubo(sc)
    return sc, qubo, Q.solve_qaoa(qubo, seed=42, shots=1024, reps=1, maxiter=80)


def test_circuit_is_parameterised_qaoa_from_actual_hamiltonian():
    qubo = M.build_qubo(ref.reference_scenario())
    ham = M.build_hamiltonian(qubo)
    for reps in (1, 2):
        circ = Q.build_qaoa_circuit(ham, reps)
        assert circ.num_qubits == 8
        assert len(circ.parameters) == 2 * reps
        names = {p.name for p in circ.parameters}
        assert {f"γ[{k}]" for k in range(reps)} <= names
        assert {f"β[{k}]" for k in range(reps)} <= names
    # The cost layer is the evolution of our operator: decomposing it must yield
    # one RZZ per ZZ term and one RZ per Z term of H_C.
    circ = Q.build_qaoa_circuit(ham, 1).decompose(reps=3)
    ops = circ.count_ops()
    n_zz = sum(1 for lab, _ in ham.operator.to_list() if lab.count("Z") == 2)
    assert ops.get("rzz", 0) + ops.get("cx", 0) // 2 >= n_zz


def test_expectation_matches_statevector_on_diagonal():
    """The estimator objective equals Σ_k |ψ_k|^2 (diag_k + offset) for the bound circuit."""
    from qiskit.quantum_info import Statevector

    qubo = M.build_qubo(ref.reference_scenario())
    ham = M.build_hamiltonian(qubo)
    circ = Q.build_qaoa_circuit(ham, 1, ham.max_abs_coefficient())
    vals = {p.name: v for p, v in zip(circ.parameters, (0.37, -0.81))}
    bound = circ.assign_parameters([vals[p.name] for p in circ.parameters])
    probs = Statevector(bound).probabilities()
    manual = float(np.dot(probs, ham.diagonal() + ham.offset))
    from qiskit.primitives import StatevectorEstimator

    ev = StatevectorEstimator().run([(circ, ham.operator, [vals[p.name] for p in circ.parameters])])
    assert float(ev.result()[0].data.evs) + ham.offset == pytest.approx(manual, abs=1e-9)


def test_qaoa_run_produces_real_samples(qaoa_run):
    _, qubo, r = qaoa_run
    assert r.ran_qiskit and r.backend == Q.SAMPLER_NAME
    assert r.n_qubits == 8 and r.reps == 1 and r.shots == 1024
    assert sum(s.count for s in r.samples) == 1024
    assert sum(s.probability for s in r.samples) == pytest.approx(1.0)
    assert len(r.samples) > 1  # a distribution, not a single injected answer
    assert r.optimizer_evaluations >= 1 and r.warm_start_evaluations >= 1
    assert r.circuit_depth > 0 and r.circuit_two_qubit_gates > 0
    assert len(r.expectation_trace) == r.optimizer_evaluations
    assert min(r.expectation_trace) == pytest.approx(r.optimal_expectation)
    for s in r.samples:
        assert s.bits == M.qiskit_bitstring_to_bits(s.bitstring_qiskit)
        assert s.qubo_energy == pytest.approx(qubo.energy(s.bits))


def test_optimised_expectation_beats_uniform_superposition(qaoa_run):
    """COBYLA must improve on <+|H|+> (γ=β=0), i.e. the quantum circuit does work."""
    _, qubo, r = qaoa_run
    uniform = float(np.mean([qubo.energy(b) for b in M.all_bitstrings(8)]))
    assert r.optimal_expectation < uniform


def test_qaoa_is_reproducible_with_fixed_seed(qaoa_run):
    _, qubo, r = qaoa_run
    again = Q.solve_qaoa(qubo, seed=42, shots=1024, reps=1, maxiter=80)
    assert again.counts == r.counts
    assert again.optimal_params == r.optimal_params


def test_qaoa_does_not_call_exact_solver(monkeypatch):
    import src.baseline as B

    def boom(*a, **k):
        raise AssertionError("QAOA must not use the exact solver")

    monkeypatch.setattr(B, "solve_exact", boom)
    qubo = M.build_qubo(ref.reference_scenario())
    sc = ref.reference_scenario()
    r = Q.solve_qaoa(qubo, seed=1, shots=256, reps=1, maxiter=20)
    Q.select_feasible(r, sc, is_feasible=ref.ref_is_feasible, score_feasible=ref.ref_score_feasible)


def test_select_feasible_never_labels_infeasible(qaoa_run):
    sc, _, r = qaoa_run
    sel = Q.select_feasible(r, sc, is_feasible=ref.ref_is_feasible, score_feasible=ref.ref_score_feasible)
    assert sel.status == "feasible_found"
    assert ref.ref_is_feasible(sel.best_bits, sc)
    feasible_shots = sum(s.count for s in r.samples if ref.ref_is_feasible(s.bits, sc))
    assert sel.feasible_sample_fraction == pytest.approx(feasible_shots / r.shots)
    best_sampled = max(
        ref.ref_score_feasible(s.bits, sc)["total_utility"]
        for s in r.samples
        if ref.ref_is_feasible(s.bits, sc)
    )
    assert sel.utility == pytest.approx(best_sampled)


def test_select_feasible_reports_no_feasible_sample():
    qubo = M.build_qubo(ref.reference_scenario())
    sc = ref.reference_scenario()
    bad = Q.Sample(bits=(1, 1, 0, 0, 0, 0, 0, 0), bitstring_qiskit="00000011", count=10,
                   probability=1.0, qubo_energy=qubo.energy((1, 1, 0, 0, 0, 0, 0, 0)))
    fake = Q.QuantumResult(
        ran_qiskit=True, backend="test", n_qubits=8, reps=1, shots=10, seed=0, maxiter=1,
        hamiltonian_scale=1.0, initial_params={}, optimal_params={}, optimal_expectation=0.0,
        warm_start_evaluations=0, optimizer_evaluations=0, optimizer_success=True,
        optimizer_message="", expectation_trace=(), samples=(bad,),
    )
    sel = Q.select_feasible(fake, sc, is_feasible=ref.ref_is_feasible, score_feasible=ref.ref_score_feasible)
    assert sel.status == "no_feasible_sample"
    assert sel.best_bits is None and sel.utility is None
    assert sel.feasible_sample_fraction == 0.0
    assert sel.lowest_energy_sample_feasible is False


def test_interp_schedule():
    out = Q._interp(np.array([1.0]))
    assert out == pytest.approx([1.0, 1.0])
    out = Q._interp(np.array([1.0, 2.0]))
    assert out == pytest.approx([1.0, 1.5, 2.0])
