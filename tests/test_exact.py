"""Tests for src/baseline.py (independent exact solver). Owner: Zaheen."""

from __future__ import annotations

import pytest

from src import baseline as B
from src import model as M
from src import quantum as Q
from tests import reference_contract as ref

EV = {"is_feasible": ref.ref_is_feasible, "score_feasible": ref.ref_score_feasible}


def test_enumerates_all_256_states_and_counts():
    ex = B.solve_exact(ref.reference_scenario(), **EV)
    assert ex.enumerated_states == 256
    # 3 options per drone (idle/r1/r2) = 81, minus 9 double-valley, minus 9 double-payload
    assert ex.feasible_states == 63
    assert ex.infeasible_states == 256 - 63


def test_base_optimum_hand_verified():
    ex = B.solve_exact(ref.reference_scenario(), **EV)
    # A hill relay, B valley relay, C east recon, D delivery:
    # (-1) + (-0.75) + 5.25 + 4.0 + 22 = 29.5
    assert ex.best_bits == (1, 0, 1, 0, 0, 1, 1, 0)
    assert ex.utility == pytest.approx(29.5)
    bd = ex.breakdown
    assert bd["mission_score"] - bd["energy_penalty"] + bd["connectivity_bonus"] == pytest.approx(29.5)
    assert bd["connected_teams"] == 1


def test_exact_is_true_maximum_over_feasible_set():
    sc = ref.reference_scenario()
    ex = B.solve_exact(sc, **EV)
    brute = max(
        ref.ref_score_feasible(b, sc)["total_utility"]
        for b in M.all_bitstrings(8)
        if ref.ref_is_feasible(b, sc)
    )
    assert ex.utility == pytest.approx(brute)
    assert ref.ref_is_feasible(ex.best_bits, sc)


def test_relay_failure_never_uses_b_and_reconnects_via_c():
    sc = ref.reference_scenario("relay_failure")
    ex = B.solve_exact(sc, **EV)
    assert ex.best_bits[2] == 0 and ex.best_bits[3] == 0
    assert ex.feasible_states == 27  # B idle -> 3^3
    # A hill, C backup valley, D delivery: -1 - 0.5 + 4 + 22 = 24.5
    assert ex.best_bits == (1, 0, 0, 0, 1, 0, 1, 0)
    assert ex.utility == pytest.approx(24.5)


def test_mission_first_policy_abandons_relay():
    ex = B.solve_exact(ref.reference_scenario("base", "mission_first"), **EV)
    assert ex.best_bits == (0, 1, 0, 1, 0, 1, 0, 1)  # all reconnaissance/delivery
    assert ex.breakdown["connected_teams"] == 0
    assert ex.utility == pytest.approx(6.5 + 3.75 + 5.25 + 2.75)


def test_blocked_link_changes_optimum_consistently():
    sc = ref.reference_scenario(blocked_edges={("B_V", "Team")})
    ex = B.solve_exact(sc, **EV)
    assert ex.best_bits[2] == 0  # B's valley relay no longer completes a path
    assert ex.breakdown["connected_teams"] == 1
    assert ex.best_bits[0] == 1 and ex.best_bits[4] == 1


def test_uses_true_utility_not_qubo_energy(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("exact baseline must not evaluate QUBO energies")

    monkeypatch.setattr(M, "qubo_energy", boom)
    monkeypatch.setattr(Q, "solve_qaoa", boom)
    ex = B.solve_exact(ref.reference_scenario(), **EV)
    assert ex.utility == pytest.approx(29.5)


def test_rejects_infeasible_states():
    sc = ref.reference_scenario()
    calls = []

    def score(bits, scenario):
        calls.append(bits)
        return ref.ref_score_feasible(bits, scenario)  # raises on infeasible input

    ex = B.solve_exact(sc, is_feasible=ref.ref_is_feasible, score_feasible=score)
    assert len(calls) == ex.feasible_states
    assert all(ref.ref_is_feasible(b, sc) for b in calls)


def test_deterministic_tie_breaking():
    a, b = (0, 1, 0, 0, 0, 0, 0, 0), (1, 0, 0, 0, 0, 0, 0, 0)
    ex = B.solve_exact(
        ref.reference_scenario(),
        is_feasible=lambda bits, s: bits in (a, b),
        score_feasible=lambda bits, s: {"total_utility": 3.0},
    )
    assert ex.best_bits == min(a, b) == a
    assert set(ex.tied_optimal_bits) == {a, b}


def test_no_feasible_assignment_reported():
    ex = B.solve_exact(
        ref.reference_scenario(),
        is_feasible=lambda bits, s: False,
        score_feasible=lambda bits, s: {"total_utility": 0.0},
    )
    assert ex.status == "no_feasible_assignment"
    assert ex.best_bits is None and ex.utility is None
    assert ex.infeasible_states == 256


def test_compare_results_gap_cases():
    ex = B.solve_exact(ref.reference_scenario(), **EV)
    same = B.compare_results(ex, 29.5)
    assert same["absolute_gap"] == 0.0 and same["relative_gap_pct"] == 0.0
    assert same["matches_exact_optimum"] is True
    worse = B.compare_results(ex, 23.6)
    assert worse["absolute_gap"] == pytest.approx(5.9)
    assert worse["relative_gap_pct"] == pytest.approx(20.0)
    none = B.compare_results(ex, None)
    assert none["absolute_gap"] is None and none["matches_exact_optimum"] is False

    zero = B.solve_exact(
        ref.reference_scenario(),
        is_feasible=lambda bits, s: bits == (0,) * 8,
        score_feasible=lambda bits, s: {"total_utility": 0.0},
    )
    z = B.compare_results(zero, 0.0)
    assert z["relative_gap_pct"] is None and z["absolute_gap"] == 0.0


def test_rank_of_utility():
    ex = B.solve_exact(ref.reference_scenario(), **EV)
    assert B.rank_of_utility(ex, 29.5) == 1
    assert B.rank_of_utility(ex, None) is None
    assert B.rank_of_utility(ex, ex.feasible_ranking[-1][1]) > 1


@pytest.mark.parametrize("name", ["base", "relay_failure"])
def test_quantum_never_beats_exact_on_same_utility(name):
    """End-to-end real QAOA: the best feasible sample is bounded by the exact optimum."""
    sc = ref.reference_scenario(name)
    ex = B.solve_exact(sc, **EV)
    r = Q.solve_qaoa(M.build_qubo(sc), seed=42, shots=1024, reps=1, maxiter=80)
    sel = Q.select_feasible(r, sc, **EV)
    if sel.status == "no_feasible_sample":
        pytest.skip("no feasible QAOA sample for this seed (allowed, reported honestly)")
    cmp = B.compare_results(ex, sel.utility)
    assert cmp["absolute_gap"] >= 0.0
    assert sel.best_bits[2] == 0 or name == "base"  # failure mask holds for sampled plan too
