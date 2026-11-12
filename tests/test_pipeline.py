"""Pipeline tests (shared file: Sufiyan + Ismail)."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src import pipeline
from src.evaluate import score_feasible
from src.scenario import load_scenario


# =============================================================================
# Ismail — src/pipeline.py logic tests
#
# Everything below uses small FAKE solver objects injected via solver_modules.
# They test the pipeline's OWN logic (decoding, filtering, gap math, schema,
# file naming). They are NOT quantum or exact results and prove nothing about
# QAOA. Test names carry "fake_logic_only" to make that explicit.
# =============================================================================

EXACT_BEST = (1, 0, 1, 0, 0, 1, 1, 0)      # base/balanced optimum, U = 29.5
SUBOPT = (0, 1, 0, 1, 0, 1, 0, 1)          # feasible, lower utility under balanced
INFEASIBLE = (1, 1, 1, 1, 1, 1, 1, 1)      # violates every exclusion
INFEASIBLE_2 = (0, 0, 1, 0, 1, 0, 0, 0)    # two valley relays

SCHEMA = {
    "scenario": None, "seed": None,
    "model": ["n_binary", "penalty", "weights", "role_order"],
    "quantum": ["ran_qiskit", "best_feasible_bits", "utility", "feasible_sample_fraction",
                "shots", "qaoa_reps", "optimizer_iterations", "elapsed_seconds"],
    "exact": ["best_bits", "utility", "enumerated_states", "elapsed_seconds"],
    "comparison": ["absolute_gap", "relative_gap_pct"],
    "constraint_checks": None, "software_versions": None, "notes": None,
}


def _fakes(samples: list[tuple[tuple[int, ...], int]], exact_bits=EXACT_BEST,
           ran_qiskit: bool = True) -> dict:
    """Fake model/baseline/quantum modules; values are arbitrary test fixtures."""
    def build_qubo(scenario):
        return SimpleNamespace(n=8, penalty=45.0, weights={"W": scenario.relay_weight},
                               ordering=("A_H", "A_N", "B_V", "B_Delivery", "C_V", "C_E",
                                         "D_Delivery", "D_S"))

    def solve_exact(scenario):
        return SimpleNamespace(best_bits=exact_bits, utility=None, enumerated_states=256,
                               feasible_states=63, infeasible_states=193,
                               elapsed_seconds=0.0)

    def solve_qaoa(qubo, *, seed, shots, reps, maxiter):
        return SimpleNamespace(
            ran_qiskit=ran_qiskit, shots=shots, reps=reps, maxiter=maxiter,
            optimizer_evaluations=1, elapsed_seconds=0.0, backend="FAKE",
            samples=[SimpleNamespace(bits=b, count=c) for b, c in samples])

    return {"model": SimpleNamespace(build_qubo=build_qubo,
                                     build_hamiltonian=lambda q: SimpleNamespace(offset=0.0)),
            "baseline": SimpleNamespace(solve_exact=solve_exact),
            "quantum": SimpleNamespace(solve_qaoa=solve_qaoa)}


def _gaps(rec):
    """The two original comparison keys (the record also carries additive text keys)."""
    return {k: rec["comparison"][k] for k in ("absolute_gap", "relative_gap_pct")}


def _run(samples, tmp_path=None, **kw):
    kw.setdefault("write", False)
    if tmp_path is not None:
        kw["out_dir"] = tmp_path / "artifacts" / "runs"
    return pipeline.run_scenario(kw.pop("name", "base"), kw.pop("policy", "balanced"),
                                 kw.pop("seed", 42), solver_modules=_fakes(samples, **{
                                     k: kw.pop(k) for k in ("exact_bits", "ran_qiskit")
                                     if k in kw}), **kw)


def test_fake_logic_only_schema_keys_present():
    rec = _run([(SUBOPT, 10)])
    for key, sub in SCHEMA.items():
        assert key in rec, key
        for s in sub or ():
            assert s in rec[key], f"{key}.{s}"
    for extra in ("scenario_meta", "timestamp"):
        assert extra in rec
    assert {"breakdown", "feasible_sample_fraction"} <= rec["quantum"].keys()
    assert {"breakdown", "feasible_states", "infeasible_states"} <= rec["exact"].keys()
    assert {"python", "numpy", "scipy", "qiskit", "qiskit_algorithms",
            "qiskit_algorithms_used"} <= set(rec["software_versions"])
    assert rec["software_versions"]["qiskit_algorithms_used"] is False
    assert "+" in rec["timestamp"] or rec["timestamp"].endswith("Z") or "-" in rec["timestamp"][19:]
    json.dumps(rec)  # serialisable


def test_fake_logic_only_infeasible_samples_filtered():
    # Infeasible samples have the highest counts; they must never be chosen.
    rec = _run([(INFEASIBLE, 500), (INFEASIBLE_2, 300), (SUBOPT, 24)])
    q = rec["quantum"]
    assert q["best_feasible_bits"] == list(SUBOPT)
    assert q["utility"] == score_feasible(SUBOPT, load_scenario("base"))["total_utility"]
    assert q["feasible_sample_fraction"] == pytest.approx(24 / 824)
    assert [r["feasible"] for r in q["sample_ranking"]] == [True, False, False]
    assert rec["constraint_checks"]["quantum_plan_feasible"] is True


def test_fake_logic_only_best_feasible_is_highest_true_utility():
    rec = _run([(SUBOPT, 900), (EXACT_BEST, 1)])
    assert rec["quantum"]["best_feasible_bits"] == list(EXACT_BEST)
    assert rec["quantum"]["best_sample_count"] == 1


def test_fake_logic_only_no_feasible_sample_is_null_never_exact():
    rec = _run([(INFEASIBLE, 600), (INFEASIBLE_2, 424)])
    q = rec["quantum"]
    assert q["best_feasible_bits"] is None and q["utility"] is None and q["breakdown"] is None
    assert q["status"] == "no_feasible_sample"
    assert q["feasible_sample_fraction"] == 0.0
    assert rec["exact"]["best_bits"] == list(EXACT_BEST)      # exact still reported ...
    assert q["best_feasible_bits"] != rec["exact"]["best_bits"]  # ... but not copied over
    assert _gaps(rec) == {"absolute_gap": None, "relative_gap_pct": None}
    assert any("no feasible sample" in n for n in rec["notes"])
    assert rec["constraint_checks"]["quantum_plan_feasible"] is False


def test_fake_logic_only_qiskit_not_run_gives_null_quantum_fields():
    rec = _run([(EXACT_BEST, 1024)], ran_qiskit=False)
    q = rec["quantum"]
    assert q["ran_qiskit"] is False
    for k in ("best_feasible_bits", "utility", "feasible_sample_fraction", "shots",
              "qaoa_reps", "optimizer_iterations", "elapsed_seconds"):
        assert q[k] is None, k


def test_fake_logic_only_gap_math_uses_same_score():
    sc = load_scenario("base")
    u_e = score_feasible(EXACT_BEST, sc)["total_utility"]
    u_q = score_feasible(SUBOPT, sc)["total_utility"]
    rec = _run([(SUBOPT, 5)])
    assert rec["exact"]["utility"] == u_e == 29.5
    assert rec["comparison"]["absolute_gap"] == pytest.approx(u_e - u_q)
    assert rec["comparison"]["relative_gap_pct"] == pytest.approx(100 * (u_e - u_q) / abs(u_e))
    assert _gaps(_run([(EXACT_BEST, 5)])) == {"absolute_gap": 0.0, "relative_gap_pct": 0.0}


def test_fake_logic_only_zero_exact_utility_gives_null_relative_gap():
    zero = (0,) * 8  # feasible idle plan, U = 0
    rec = _run([(zero, 5)], exact_bits=zero)
    assert _gaps(rec) == {"absolute_gap": 0.0, "relative_gap_pct": None}
    assert any("relative_gap_pct" in n for n in rec["notes"])


def test_fake_logic_only_constraint_checks_explicit_booleans():
    c = _run([((0, 1, 0, 0, 0, 1, 1, 0), 5), (SUBOPT, 50)], name="relay_failure",  # SUBOPT uses B
             exact_bits=(1, 0, 0, 0, 1, 0, 1, 0))["constraint_checks"]
    for k in ("quantum_plan_feasible", "exact_plan_feasible", "failure_mask_respected",
              "one_role_per_drone", "single_valley", "single_payload",
              "exact_states_enumerated_256"):
        assert c[k] is True, k


def test_fake_logic_only_file_naming_rule(tmp_path):
    assert pipeline.run_filename("base", "balanced", 42) == "base.json"
    assert pipeline.run_filename("base", "balanced", 7) == "base__balanced__seed7.json"
    assert (pipeline.run_filename("relay_failure", "mission_first", 42)
            == "relay_failure__mission_first__seed42.json")
    rec = _run([(SUBOPT, 5)], tmp_path, write=True, policy="coverage_first", seed=3)
    out = tmp_path / "artifacts" / "runs" / "base__coverage_first__seed3.json"
    assert out.exists()
    assert json.loads(out.read_text(encoding="utf-8"))["quantum"]["best_feasible_bits"] \
        == rec["quantum"]["best_feasible_bits"]


def test_fake_logic_only_write_false_writes_nothing(tmp_path):
    _run([(SUBOPT, 5)], tmp_path, write=False)
    assert not (tmp_path / "artifacts").exists()


def test_fake_logic_only_refuses_output_outside_artifacts_runs(tmp_path):
    with pytest.raises(ValueError):
        pipeline.run_scenario("base", "balanced", write=True, out_dir=tmp_path / "elsewhere",
                              solver_modules=_fakes([(SUBOPT, 5)]))
    assert not any(tmp_path.iterdir())


def test_fake_logic_only_missing_solver_module_raises_clear_error(monkeypatch):
    real = pipeline.importlib.import_module

    def fake_import(name, *a, **k):
        if name == "src.quantum":
            raise ImportError("No module named 'qiskit'")
        return real(name, *a, **k)

    monkeypatch.setattr(pipeline.importlib, "import_module", fake_import)
    fakes = _fakes([])
    with pytest.raises(RuntimeError, match=r"src/quantum\.py \(owner: Zaheen\)"):
        pipeline.run_scenario("base", "balanced", write=False,
                              solver_modules={k: fakes[k] for k in ("model", "baseline")})


def test_scenario_exposes_model_fields():
    """G0 adapter fields read by src/model.py (relay_reward, relay_pairs, role key)."""
    base, shadow = load_scenario("base"), load_scenario("shadow_block")
    assert base.relay_reward == base.relay_weight == 22
    assert base.relay_pairs == [(0, 2), (0, 4)]
    assert shadow.relay_pairs == [(0, 4)]
    assert [r.key for r in base.roles] == ["A_H", "A_N", "B_V", "B_Delivery", "C_V", "C_E",
                                           "D_Delivery", "D_S"]


# =============================================================================
# Ismail — cross-checks of Zaheen's REAL modules against Ismail's evaluator
#
# These use the real src/model.py and src/baseline.py (no fakes, no QAOA).
# Skipped only if Qiskit is not installed. A failure here is a real
# model/evaluator mismatch: report it, do not weaken the assertion.
# =============================================================================

from itertools import product as _product  # noqa: E402

from src.evaluate import is_feasible  # noqa: E402

model = pytest.importorskip("src.model", reason="Qiskit not installed")
baseline = pytest.importorskip("src.baseline", reason="Qiskit not installed")

CROSS_CASES = [(s, p) for s in ("base", "relay_failure", "shadow_block")
               for p in ("mission_first", "balanced", "coverage_first")]
EXPECTED_FEASIBLE = {"base": 63, "relay_failure": 27, "shadow_block": 63}
ALL_STATES = list(_product((0, 1), repeat=8))


def _my_bruteforce(sc):
    """Ismail's own 256-state search: (best bits, best U, feasible count). Ties -> smallest tuple."""
    feas = [(b, score_feasible(b, sc)["total_utility"]) for b in ALL_STATES if is_feasible(b, sc)]
    best_u = max(u for _, u in feas)
    best = min(b for b, u in feas if abs(u - best_u) <= 1e-9)
    return best, best_u, len(feas)


@pytest.mark.parametrize("name,policy", CROSS_CASES)
def test_cross_qubo_argmin_is_my_feasible_optimum(name, policy):
    """(a) argmin of Zaheen's QUBO energy over ALL 256 states = my best feasible plan."""
    sc = load_scenario(name, policy)
    qubo = model.build_qubo(sc)
    energies = {b: model.qubo_energy(qubo, b) for b in ALL_STATES}
    e_min = min(energies.values())
    argmins = sorted(b for b, e in energies.items() if abs(e - e_min) <= 1e-9)
    best, best_u, _ = _my_bruteforce(sc)
    assert all(is_feasible(b, sc) for b in argmins), \
        f"P={qubo.penalty} too small: infeasible minimiser(s) {argmins}"
    assert argmins == [best], f"QUBO argmin {argmins} != my best {best}"
    assert e_min == pytest.approx(-best_u)


@pytest.mark.parametrize("name,policy", CROSS_CASES)
def test_cross_qubo_energy_equals_minus_my_utility_on_feasible_states(name, policy):
    """(a, stronger) For every feasible state, E(x) == -U(x) from my score_feasible."""
    sc = load_scenario(name, policy)
    qubo = model.build_qubo(sc)
    bad = [(b, model.qubo_energy(qubo, b), score_feasible(b, sc)["total_utility"])
           for b in ALL_STATES if is_feasible(b, sc)
           and abs(model.qubo_energy(qubo, b) + score_feasible(b, sc)["total_utility"]) > 1e-9]
    assert not bad, f"E != -U on feasible states (bits, E, U): {bad[:5]}"


@pytest.mark.parametrize("name,policy", CROSS_CASES)
def test_cross_solve_exact_matches_my_bruteforce(name, policy):
    """(b) + (c) bits, utility, and feasible/infeasible counts."""
    sc = load_scenario(name, policy)
    ex = baseline.solve_exact(sc)
    best, best_u, n_feas = _my_bruteforce(sc)
    assert tuple(ex.best_bits) == best
    assert ex.utility == pytest.approx(best_u)
    assert ex.enumerated_states == 256
    assert ex.feasible_states == n_feas == EXPECTED_FEASIBLE[name]
    assert ex.infeasible_states == 256 - EXPECTED_FEASIBLE[name]


@pytest.mark.parametrize("hot", [0, 7])
def test_cross_bit_order_one_hot_through_qiskit(hot):
    """(d) Only x0=1 / only x7=1: a real Qiskit measurement decodes back to the same index."""
    from qiskit import QuantumCircuit
    from qiskit.quantum_info import Statevector

    qc = QuantumCircuit(8)
    qc.x(hot)  # qubit i is x_i
    (printed,) = Statevector(qc).probabilities_dict()  # single basis state, Qiskit-printed
    bits = model.qiskit_bitstring_to_bits(printed)
    assert [i for i, b in enumerate(bits) if b] == [hot]
    assert model.bits_to_qiskit_bitstring(bits) == printed
    assert model.index_to_bits(model.bits_to_index(bits), 8) == bits
    assert model.bits_to_index(bits) == 1 << hot



# =============================================================================
# Ismail — P1 self-healing and P2 policy-sweep logic (FAKE solvers: logic only)
#
# The fake exact solver brute-forces with Ismail's evaluator, and the fake
# "QAOA" returns that plan plus infeasible noise. These test the pipeline's
# bookkeeping only. They are NOT quantum results.
# =============================================================================

from dataclasses import replace as _replace  # noqa: E402


def _bf_best(sc):
    feas = [(b, score_feasible(b, sc)["total_utility"])
            for b in _product((0, 1), repeat=8) if is_feasible(b, sc)]
    u = max(x for _, x in feas)
    return min(b for b, x in feas if abs(x - u) <= 1e-9), u, len(feas)


def _bf_fakes(calls: list | None = None, quantum_feasible: bool = True) -> dict:
    """Fakes whose exact/quantum plans follow the scenario actually passed in."""
    def build_qubo(sc):
        return SimpleNamespace(n=8, penalty=45.0, weights={"W": sc.relay_weight},
                               ordering=tuple(r.key for r in sc.roles), sc=sc)

    def solve_exact(sc):
        best, _, n = _bf_best(sc)
        return SimpleNamespace(best_bits=best, utility=None, enumerated_states=256,
                               feasible_states=n, infeasible_states=256 - n,
                               elapsed_seconds=0.0)

    def solve_qaoa(qubo, *, seed, shots, reps, maxiter):
        if calls is not None:
            calls.append((qubo.sc.name, qubo.sc.policy, seed))
        samples = [SimpleNamespace(bits=INFEASIBLE, count=shots // 2)]
        if quantum_feasible:
            samples.append(SimpleNamespace(bits=_bf_best(qubo.sc)[0], count=shots - shots // 2))
        return SimpleNamespace(ran_qiskit=True, shots=shots, reps=reps, maxiter=maxiter,
                               optimizer_evaluations=1, elapsed_seconds=0.0, backend="FAKE",
                               samples=samples)

    return {"model": SimpleNamespace(build_qubo=build_qubo,
                                     build_hamiltonian=lambda q: SimpleNamespace(offset=0.0)),
            "baseline": SimpleNamespace(solve_exact=solve_exact),
            "quantum": SimpleNamespace(solve_qaoa=solve_qaoa)}


def test_fake_logic_only_healing_three_stages(tmp_path):
    calls: list = []
    rec = pipeline.run_scenario("relay_failure", "balanced", 42, write=True,
                                out_dir=tmp_path / "artifacts" / "runs",
                                solver_modules=_bf_fakes(calls))
    # base was solved in the same call, same policy and seed, and NOT written
    assert calls == [("relay_failure", "balanced", 42), ("base", "balanced", 42)]
    assert sorted(p.name for p in (tmp_path / "artifacts" / "runs").iterdir()) \
        == ["relay_failure.json"]
    h = rec["healing"]
    for br in ("quantum", "exact"):
        assert h["before"][br]["bits"] == [1, 0, 1, 0, 0, 1, 1, 0]
        assert h["before"][br]["connected_teams"] == 1
        d = h["immediately_after_failure"][br]
        assert d["lost_roles"] == ["B_V"] and d["connectivity_lost"] is True
        assert d["bits"] == [1, 0, 0, 0, 0, 1, 1, 0] and d["connected_teams"] == 0
        r = h["replanned"][br]
        assert r["bits"] == rec[br]["best_feasible_bits" if br == "quantum" else "best_bits"]
        assert r["bits"][2:4] == [0, 0] and r["connected_teams"] == 1
        assert h["lost_mission_utility"][br] is True
        assert h["recovered_connectivity"][br] is True
    # replanned stage is the relay_failure run's own top-level result
    assert h["replanned"]["exact"]["breakdown"] == rec["exact"]["breakdown"]


def test_fake_logic_only_healing_no_feasible_base_quantum_is_null():
    rec = pipeline.run_scenario("relay_failure", "balanced", 42, write=False,
                                solver_modules=_bf_fakes(quantum_feasible=False))
    h = rec["healing"]
    assert h["before"]["quantum"]["bits"] is None
    assert h["immediately_after_failure"]["quantum"] is None
    assert h["recovered_connectivity"]["quantum"] is None
    assert h["recovered_connectivity"]["exact"] is True  # exact branch unaffected
    assert any("quantum: no feasible base plan" in n for n in h["notes"])


def test_fake_logic_only_base_run_has_no_healing():
    assert "healing" not in pipeline.run_scenario("base", "balanced", write=False,
                                                  solver_modules=_bf_fakes())


def test_fake_logic_only_policy_sweep_files_and_table(tmp_path):
    calls: list = []
    sw = pipeline.run_policy_sweep("base", 42, write=True,
                                   out_dir=tmp_path / "artifacts" / "runs",
                                   solver_modules=_bf_fakes(calls))
    assert [c[1] for c in calls] == ["mission_first", "balanced", "coverage_first"]
    assert sorted(p.name for p in (tmp_path / "artifacts" / "runs").iterdir()) == [
        "base.json", "base__coverage_first__seed42.json", "base__mission_first__seed42.json"]
    rows = {r["policy"]: r for r in sw["rows"]}
    assert [rows[p]["W"] for p in ("mission_first", "balanced", "coverage_first")] == [3, 22, 35]
    bal = rows["balanced"]["exact"]
    assert bal["forfeited_roles"] == [] and bal["mission_score_delta"] == 0
    # differences are computed from the bits, not hard-coded
    for p, r in rows.items():
        x = r["exact"]
        assert set(x["forfeited_roles"]) == set(bal["roles"]) - set(x["roles"])
        assert x["connected_teams"] == score_feasible(
            tuple(x["bits"]), load_scenario("base", p))["connected_teams"]
    for u in sw["unchanged"]:
        a, b = u["policies"]
        assert rows[a][u["branch"]]["bits"] == rows[b][u["branch"]]["bits"]
        assert u["reason"].startswith("plan unchanged")
    # every pair with identical exact plans is reported, and only those
    ex = {p: tuple(r["exact"]["bits"]) for p, r in rows.items()}
    names = list(ex)
    same = {tuple(u["policies"]) for u in sw["unchanged"] if u["branch"] == "exact"}
    assert same == {(a, b) for i, a in enumerate(names) for b in names[i + 1:] if ex[a] == ex[b]}


# =============================================================================
# Ismail — constraints under all policies, REAL exact solver only (no QAOA)
# =============================================================================

@pytest.mark.parametrize("name", ["base", "relay_failure", "shadow_block"])
@pytest.mark.parametrize("policy", ["mission_first", "balanced", "coverage_first"])
def test_exact_plan_constraints_all_policies(name, policy):
    sc = load_scenario(name, policy)
    bits = tuple(baseline.solve_exact(sc).best_bits)
    assert is_feasible(bits, sc)
    checks = pipeline._plan_checks(bits, sc)
    assert all(checks.values()), checks
    if name == "relay_failure":
        assert bits[2] == bits[3] == 0


# Ismail's brief said the flip is between W=11/12 (base) and 14/15 (relay_failure).
# The data give W* = 10.75 and 13.25, i.e. one lower; see COMPLETION_REPORT.md.
@pytest.mark.parametrize("name,w_lo,w_hi,w_star",
                         [("base", 10, 11, 10.75), ("relay_failure", 13, 14, 13.25)])
def test_exact_optimum_connectivity_flip_weight(name, w_lo, w_hi, w_star):
    """Exact optimum is disconnected at w_lo and connected at w_hi; W* from the data."""
    sc = load_scenario(name, "balanced")
    s0 = _replace(sc, relay_weight=0)
    assert pipeline._best_u(s0, 0) - pipeline._best_u(s0, 1) == pytest.approx(w_star)
    conn = {}
    for w in (w_lo, w_hi):
        s = _replace(sc, relay_weight=w)
        conn[w] = score_feasible(tuple(baseline.solve_exact(s).best_bits), s)["connected_teams"]
    assert conn == {w_lo: 0, w_hi: 1}


def test_unchanged_reason_is_computed_from_data():
    sc = load_scenario("base", "balanced")
    bits = tuple(baseline.solve_exact(sc).best_bits)
    txt = pipeline.unchanged_reason("base", "balanced", "coverage_first", bits)
    alt = pipeline._best_u(sc, 0)
    assert txt.startswith("plan unchanged") and f"U={alt:g}" in txt and "W=22" in txt


# =============================================================================
# Ismail — run record: diagnostics, interpretation, notes, paths (FAKE solvers)
#
# Logic only. The fake samples are fixtures, not quantum results.
# =============================================================================

ORIGINAL_KEYS = {
    "scenario": None, "policy": None, "seed": None, "timestamp": None,
    "model": ["n_binary", "penalty", "weights", "role_order", "penalty_bound", "ising_offset"],
    "quantum": ["ran_qiskit", "best_feasible_bits", "utility", "feasible_sample_fraction",
                "shots", "qaoa_reps", "optimizer_iterations", "elapsed_seconds", "breakdown",
                "status", "best_sample_count", "distinct_bitstrings_sampled", "backend",
                "maxiter", "circuit_depth", "optimal_params", "selection_rule",
                "sample_ranking"],
    "exact": ["best_bits", "utility", "enumerated_states", "elapsed_seconds", "breakdown",
              "feasible_states", "infeasible_states"],
    "comparison": ["absolute_gap", "relative_gap_pct"],
    "constraint_checks": ["quantum_plan_feasible", "exact_plan_feasible",
                          "quantum_best_feasible_rechecked", "exact_best_feasible_rechecked",
                          "plans_checked", "all_labelled_feasible_samples_pass"],
    "software_versions": None, "notes": None, "scenario_meta": None, "output_file": None,
}


def test_fake_logic_only_original_contract_keys_remain():
    rec = _run([(SUBOPT, 10)])
    for key, subs in ORIGINAL_KEYS.items():
        assert key in rec, key
        for s in subs or ():
            assert s in rec[key], f"{key}.{s}"


def test_fake_logic_only_diagnostics_values_by_hand():
    # shots = 1024 (default). Counts: infeasible 500 + 300, SUBOPT 24, optimum 10.
    rec = _run([(INFEASIBLE, 500), (INFEASIBLE_2, 300), (SUBOPT, 24), (EXACT_BEST, 10)])
    q = rec["quantum"]
    d = q["diagnostics"]
    assert q["best_feasible_bits"] == list(EXACT_BEST)           # selection untouched
    assert d["selection_method"].startswith("best feasible bitstring")
    assert d["shots"] == 1024 and d["distinct_samples"] == 4
    assert d["most_frequent_sample"] == {"bits": list(INFEASIBLE), "count": 500,
                                         "feasible": False, "utility_or_null": None}
    assert d["optimum_sample_count"] == 10
    assert d["optimum_sample_frequency"] == pytest.approx(10 / 1024)
    ub = d["uniform_baseline"]
    assert ub["feasible_fraction"] == pytest.approx(63 / 256)
    assert ub["p_hit_optimum_per_shot"] == pytest.approx(1 / 256)
    assert ub["p_hit_optimum_within_shots"] == pytest.approx(1 - (255 / 256) ** 1024)
    assert 0.981 < ub["p_hit_optimum_within_shots"] < 0.983
    assert q["feasible_sample_fraction"] == pytest.approx(34 / 834)   # kept, not recomputed


def test_fake_logic_only_diagnostics_absent_optimum_is_zero():
    d = _run([(SUBOPT, 24)])["quantum"]["diagnostics"]
    assert d["optimum_sample_frequency"] == 0 and d["optimum_sample_count"] == 0
    assert d["most_frequent_sample"]["bits"] == list(SUBOPT)
    assert d["most_frequent_sample"]["utility_or_null"] == score_feasible(
        SUBOPT, load_scenario("base"))["total_utility"]


def test_fake_logic_only_diagnostics_never_change_quantum_choice():
    # Exact optimum is rarest and not most frequent; the choice is by utility only.
    rec = _run([(SUBOPT, 900), (EXACT_BEST, 1)])
    assert rec["quantum"]["best_feasible_bits"] == list(EXACT_BEST)
    assert rec["quantum"]["diagnostics"]["most_frequent_sample"]["bits"] == list(SUBOPT)


def test_fake_logic_only_diagnostics_no_feasible_sample():
    rec = _run([(INFEASIBLE, 600), (INFEASIBLE_2, 424)])
    d = rec["quantum"]["diagnostics"]
    assert d["optimum_sample_frequency"] == 0
    assert rec["quantum"]["best_feasible_bits"] is None
    assert rec["comparison"]["absolute_gap"] is None
    assert "undefined" in rec["comparison"]["interpretation"]


def test_fake_logic_only_qiskit_not_run_has_null_diagnostics():
    rec = _run([(EXACT_BEST, 1024)], ran_qiskit=False)
    assert rec["quantum"]["diagnostics"] is None
    assert "did not run" in rec["comparison"]["interpretation"]


def test_fake_logic_only_interpretation_never_claims_advantage():
    for samples in ([(SUBOPT, 5)], [(EXACT_BEST, 5)], [(INFEASIBLE, 9)]):
        c = _run(samples)["comparison"]
        text = (c["interpretation"] + c["no_speedup_note"]).lower()
        for bad in ("outperform", "advantage over", "faster than classical", "speedup achieved"):
            assert bad not in text
        assert c["no_speedup_note"] == ("No quantum speedup is claimed; the exact enumeration "
                                        "of 256 states is classically trivial.")
        assert "timings vary" in c["timing_note"].lower()
    zero = _run([(EXACT_BEST, 5)])["comparison"]["interpretation"]
    assert "not evidence that QAOA solved" in zero and "98.2%" in zero


def test_fake_logic_only_notes_and_evaluation_counts():
    q = _run([(SUBOPT, 5)])["quantum"]
    assert "final sampling only" in q["shots_note"] and "StatevectorEstimator" in q["shots_note"]
    ev = q["evaluation_counts"]
    assert ev["optimizer_evaluations"] == 1 and ev["warm_start_evaluations"] is None
    assert ev["total_circuit_evaluations"] is None and "excludes the warm-start" in ev["note"]


def test_fake_logic_only_evaluation_counts_with_warm_start():
    fakes = _fakes([(SUBOPT, 5)])
    orig = fakes["quantum"].solve_qaoa

    def with_warm(qubo, **kw):
        r = orig(qubo, **kw)
        r.warm_start_evaluations = 144
        return r
    fakes["quantum"] = SimpleNamespace(solve_qaoa=with_warm)
    rec = pipeline.run_scenario("base", "balanced", write=False, solver_modules=fakes)
    ev = rec["quantum"]["evaluation_counts"]
    assert ev["warm_start_evaluations"] == 144 and ev["total_circuit_evaluations"] == 145


def test_fake_logic_only_penalty_derivation_copied_or_null():
    assert _run([(SUBOPT, 5)])["model"]["penalty_derivation"] is None
    fakes = _fakes([(SUBOPT, 5)])
    inner = fakes["model"].build_qubo
    fakes["model"] = SimpleNamespace(
        build_qubo=lambda sc: SimpleNamespace(**vars(inner(sc)), penalty_derivation="B + 1"),
        build_hamiltonian=fakes["model"].build_hamiltonian)
    rec = pipeline.run_scenario("base", "balanced", write=False, solver_modules=fakes)
    assert rec["model"]["penalty_derivation"] == "B + 1"


def test_fake_logic_only_output_file_outside_repo_is_filename_only(tmp_path):
    rec = _run([(SUBOPT, 5)], tmp_path, write=True)
    assert rec["output_file"] == "base.json"
    assert not Path(rec["output_file"]).is_absolute()


def test_fake_logic_only_output_file_inside_repo_is_posix_relative(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "ROOT", tmp_path)
    rec = _run([(SUBOPT, 5)], tmp_path, write=True)
    assert rec["output_file"] == "artifacts/runs/base.json"


# ---- run.py: --from-saved error handling and banner -----------------------------------

import run as run_cli  # noqa: E402


def test_run_cli_from_saved_missing_file_is_one_line_nonzero(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(run_cli, "RUNS", tmp_path)
    code = run_cli.main(["--policy-sweep", "--from-saved", "--scenario", "base", "--seed", "42"])
    err = capsys.readouterr().err
    assert code != 0 and err.startswith("error:") and len(err.strip().splitlines()) == 1
    assert "Traceback" not in err


def test_run_cli_from_saved_bad_json_and_missing_key(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(run_cli, "RUNS", tmp_path)
    for pol in pipeline.POLICIES:
        (tmp_path / pipeline.run_filename("base", pol, 42)).write_text("{not json", encoding="utf-8")
    assert run_cli.main(["--policy-sweep", "--from-saved"]) != 0
    assert "invalid JSON" in capsys.readouterr().err
    for pol in pipeline.POLICIES:
        (tmp_path / pipeline.run_filename("base", pol, 42)).write_text("{}", encoding="utf-8")
    assert run_cli.main(["--policy-sweep", "--from-saved"]) != 0
    assert "missing key" in capsys.readouterr().err


def test_run_cli_from_saved_banner_names_each_file(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(run_cli, "RUNS", tmp_path)
    for pol in pipeline.POLICIES:
        rec = pipeline.run_scenario("base", pol, 42, write=False, solver_modules=_bf_fakes())
        (tmp_path / pipeline.run_filename("base", pol, 42)).write_text(
            json.dumps(rec, default=float), encoding="utf-8")
    assert run_cli.main(["--policy-sweep", "--from-saved"]) == 0
    out = capsys.readouterr().out
    assert out.count("LOADED FROM SAVED FILE") == 3 and "(not a new run)" in out


def test_run_cli_summary_prints_diagnostics(capsys):
    rec = _run([(SUBOPT, 900), (EXACT_BEST, 1)])
    run_cli.print_run(rec)
    out = capsys.readouterr().out
    assert "most frequent" in out and "optimum frequency" in out and "No quantum speedup" in out
