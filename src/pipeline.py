"""Run orchestration and JSON results (architecture.md §6-§7).

Owner: Ismail. Calls Zaheen's model / exact / QAOA code, then judges the
quantum samples here with the original ``is_feasible`` / ``score_feasible``.
The exact answer is never used as, or in place of, a quantum result.
All scenario numbers are synthetic and illustrative.
"""
from __future__ import annotations

import importlib
import importlib.metadata
import json
import platform
from datetime import datetime
from pathlib import Path
from typing import Any

from src.evaluate import is_feasible, score_degraded, score_feasible
from src.scenario import POLICIES, ROLE_KEYS, load_scenario

ROOT = Path(__file__).resolve().parent.parent
N_BITS = 8
TOL = 1e-9
# module name -> (file, owner, functions the pipeline needs)
SOLVERS = {
    "model": ("src/model.py", "Zaheen", ("build_qubo", "build_hamiltonian")),
    "baseline": ("src/baseline.py", "Zaheen", ("solve_exact",)),
    "quantum": ("src/quantum.py", "Zaheen", ("solve_qaoa",)),
}
SELECTION_RULE = ("highest true utility (score_feasible) among sampled assignments that "
                  "pass is_feasible; ties -> higher count, then smallest canonical tuple")


def _load_solvers(injected: dict[str, Any] | None) -> dict[str, Any]:
    """Import Zaheen's modules, or use injected objects (tests only)."""
    mods: dict[str, Any] = {}
    for name, (path, owner, funcs) in SOLVERS.items():
        if injected is not None and name in injected:
            mod = injected[name]
        else:
            try:
                mod = importlib.import_module(f"src.{name}")
            except ImportError as exc:
                raise RuntimeError(f"cannot import {path} (owner: {owner}): {exc}") from exc
        missing = [f for f in funcs if not hasattr(mod, f)]
        if missing:
            raise RuntimeError(f"{path} (owner: {owner}) is missing {missing}")
        mods[name] = mod
    return mods


def run_filename(scenario: str, policy: str, seed: int) -> str:
    """CLAUDE.md rule: <scenario>.json for (balanced, 42), else <scenario>__<policy>__seed<N>.json."""
    if policy == "balanced" and seed == 42:
        return f"{scenario}.json"
    return f"{scenario}__{policy}__seed{seed}.json"


def _runs_dir(out_dir: str | Path) -> Path:
    """Resolve out_dir (relative to repo root); it must be an artifacts/runs folder."""
    path = Path(out_dir)
    path = (path if path.is_absolute() else ROOT / path).resolve()
    if path.name != "runs" or path.parent.name != "artifacts":
        raise ValueError(f"run output may only go to an artifacts/runs folder, got {path}")
    return path


def software_versions() -> dict[str, str | None]:
    """Installed versions; None when a package is not installed."""
    def ver(dist: str) -> str | None:
        try:
            return importlib.metadata.version(dist)
        except importlib.metadata.PackageNotFoundError:
            return None
    return {"python": platform.python_version(), "numpy": ver("numpy"),
            "scipy": ver("scipy"), "qiskit": ver("qiskit"),
            "qiskit_algorithms": ver("qiskit-algorithms"),
            # No module in src/ imports qiskit_algorithms (checked with grep).
            "qiskit_algorithms_used": False}


def _bits(raw: Any) -> tuple[int, ...] | None:
    return None if raw is None else tuple(int(b) for b in raw)


NO_SPEEDUP_NOTE = ("No quantum speedup is claimed; the exact enumeration of 256 states "
                   "is classically trivial.")
TIMING_NOTE = ("quantum elapsed_seconds includes the warm-start grid scan, the optimisation "
               "loop and a metadata-only transpile; exact elapsed_seconds covers only a "
               "256-state loop and is not comparable. Timings vary between runs.")
SHOTS_NOTE = ("shots applies to the final sampling only; the optimisation loop uses the "
              "exact StatevectorEstimator.")


def quantum_diagnostics(ranking: list[dict], shots: int | None, n_feasible_states: int | None,
                        exact_bits: tuple[int, ...] | None) -> dict:
    """Post-hoc diagnostics of the sampled counts. Computed AFTER the quantum selection and
    never used to choose the quantum plan."""
    total = sum(r["count"] for r in ranking)
    n = shots if shots else total
    top = sorted(ranking, key=lambda r: (-r["count"], r["bits"]))[0] if ranking else None
    opt_count = next((r["count"] for r in ranking
                      if exact_bits is not None and tuple(r["bits"]) == exact_bits), 0)
    return {
        "selection_method": "best feasible bitstring (by true utility, src/evaluate.py) "
                            "among all shots",
        "shots": shots, "distinct_samples": len(ranking),
        "most_frequent_sample": None if top is None else {
            "bits": top["bits"], "count": top["count"], "feasible": top["feasible"],
            "utility_or_null": top["utility"]},
        "optimum_sample_frequency": (opt_count / n) if (n and exact_bits is not None) else None,
        "optimum_sample_count": opt_count if exact_bits is not None else None,
        "uniform_baseline": {
            "feasible_fraction": None if n_feasible_states is None else n_feasible_states / 256,
            "p_hit_optimum_per_shot": 1 / 256,
            "p_hit_optimum_within_shots": None if not n else 1 - (255 / 256) ** n},
    }


def interpret_comparison(diag: dict | None, abs_gap: float | None) -> str:
    """Plain-language reading of the gap, generated from the data."""
    if diag is None:
        return "Qiskit did not run; there is no quantum result to compare."
    if abs_gap is None:
        return "No feasible quantum sample or no exact optimum, so the gap is undefined."
    f, base = diag["optimum_sample_frequency"], 1 / 256
    ub = diag["uniform_baseline"]
    parts = [f"The gap is {abs_gap:g} because the reported quantum plan is the best feasible "
             f"bitstring among {diag['shots']} shots, not the most frequent one."]
    if f is not None:
        parts.append(f"The exact optimum appeared in {f:.4f} of shots versus {base:.4f} for "
                     "uniform random sampling.")
    if ub["p_hit_optimum_within_shots"] is not None:
        parts.append(f"Uniform random sampling would also contain the optimum in "
                     f"{100 * ub['p_hit_optimum_within_shots']:.1f}% of runs, so a zero gap is "
                     "not evidence that QAOA solved the problem.")
    mf = diag["most_frequent_sample"]
    if mf is not None:
        parts.append(f"Most frequent sample: {mf['bits']} (feasible={mf['feasible']}, "
                     f"utility={mf['utility_or_null']}).")
    return " ".join(parts)


def _plan_checks(bits: tuple[int, ...], scenario) -> dict[str, bool]:
    """Hard constraints re-derived from raw scenario fields (independent of is_feasible)."""
    on = [r for r, x in zip(scenario.roles, bits) if x]
    drones = [r.drone for r in on]
    return {
        "failure_mask_respected": all(d not in scenario.disabled_drones for d in drones),
        "one_role_per_drone": len(drones) == len(set(drones)),
        "single_valley": bits[2] + bits[4] <= 1,
        "single_payload": bits[3] + bits[6] <= 1,
        "battery_reserve_respected": all(
            r.energy + scenario.reserve <= scenario.battery[r.drone] for r in on),
    }


def decode_samples(samples, scenario) -> tuple[list[dict], float | None]:
    """Judge every sampled bitstring; return ranking (best first) and feasible shot fraction."""
    counts: dict[tuple[int, ...], int] = {}
    for s in samples:
        b = _bits(s.bits)
        counts[b] = counts.get(b, 0) + int(s.count)
    rows = []
    for b, c in counts.items():
        ok = len(b) == N_BITS and is_feasible(b, scenario)
        u = score_feasible(b, scenario)["total_utility"] if ok else None
        rows.append({"bits": list(b), "count": c, "feasible": ok, "utility": u})
    rows.sort(key=lambda r: (not r["feasible"], -(r["utility"] or 0.0), -r["count"], r["bits"]))
    total = sum(counts.values())
    frac = sum(r["count"] for r in rows if r["feasible"]) / total if total else None
    return rows, frac


def _solve(name: str, policy: str, seed: int, shots: int, reps: int, maxiter: int,
           mods: dict[str, Any]) -> dict:
    """One real solve (exact + QAOA) of one scenario; returns the record, writes nothing."""
    notes = ["All scenario data (utilities, energies, batteries, links, weights) are "
             "synthetic and illustrative."]

    scenario = load_scenario(name, policy)
    qubo = mods["model"].build_qubo(scenario)
    ham = mods["model"].build_hamiltonian(qubo)
    exact = mods["baseline"].solve_exact(scenario)
    qres = mods["quantum"].solve_qaoa(qubo, seed=seed, shots=shots, reps=reps, maxiter=maxiter)

    # ---- quantum: decode and judge samples here ---------------------------
    ran = bool(getattr(qres, "ran_qiskit", False))
    ranking, frac = decode_samples(getattr(qres, "samples", ()), scenario) if ran else ([], None)
    best = next((r for r in ranking if r["feasible"]), None)
    q_bits = tuple(best["bits"]) if best else None
    q_score = score_feasible(q_bits, scenario) if q_bits else None
    if not ran:
        notes.append("Qiskit did not run; quantum fields are null.")
    elif q_bits is None:
        notes.append(f"QAOA produced no feasible sample among {len(ranking)} distinct "
                     "bitstrings; best_feasible_bits is null and the exact answer is NOT "
                     "substituted.")

    # ---- exact: re-score with the same evaluator --------------------------
    e_bits = _bits(exact.best_bits)
    e_score = score_feasible(e_bits, scenario) if e_bits else None
    if e_bits is None:
        notes.append("Exact search found no feasible assignment.")

    # ---- comparison (same score_feasible for both) ------------------------
    u_q = q_score["total_utility"] if q_score else None
    u_e = e_score["total_utility"] if e_score else None
    abs_gap = rel_gap = None
    if u_q is not None and u_e is not None:
        abs_gap = u_e - u_q
        if abs(abs_gap) <= TOL:
            abs_gap = 0.0
        if abs_gap < 0:
            notes.append("Quantum utility exceeds exact optimum: evaluator inconsistency.")
        if abs(u_e) > TOL:
            rel_gap = 100.0 * abs_gap / abs(u_e)
        else:
            notes.append("Exact utility is zero; relative_gap_pct is undefined (null).")
    else:
        notes.append("Gap undefined: a feasible quantum or exact plan is missing.")

    # ---- constraint checks -----------------------------------------------
    checks: dict[str, Any] = {
        "quantum_plan_feasible": bool(q_bits) and is_feasible(q_bits, scenario),
        "exact_plan_feasible": bool(e_bits) and is_feasible(e_bits, scenario),
    }
    # Names read by Sufiyan's dashboard (app.py); same values as above.
    checks["quantum_best_feasible_rechecked"] = checks["quantum_plan_feasible"]
    checks["exact_best_feasible_rechecked"] = checks["exact_plan_feasible"]
    plans = {k: b for k, b in (("quantum", q_bits), ("exact", e_bits)) if b}
    per_plan = {k: _plan_checks(b, scenario) for k, b in plans.items()}
    for key in ("failure_mask_respected", "one_role_per_drone", "single_valley",
                "single_payload", "battery_reserve_respected"):
        checks[key] = all(c[key] for c in per_plan.values())
    checks["plans_checked"] = sorted(plans)
    checks["exact_states_enumerated_256"] = exact.enumerated_states == 2 ** N_BITS
    checks["all_labelled_feasible_samples_pass"] = all(
        is_feasible(tuple(r["bits"]), scenario) for r in ranking if r["feasible"])

    def q(attr: str):
        return getattr(qres, attr, None) if ran else None

    # ---- post-hoc diagnostics (computed AFTER the quantum selection above) ----
    diag = (quantum_diagnostics(ranking, q("shots"), exact.feasible_states, e_bits)
            if ran else None)
    interpretation = interpret_comparison(diag, abs_gap)
    warm = q("warm_start_evaluations")
    evals = {"optimizer_evaluations": q("optimizer_evaluations"),
             "warm_start_evaluations": warm,
             "total_circuit_evaluations": (None if warm is None or not ran else
                                           q("optimizer_evaluations") + warm)}
    evals["note"] = (
        "optimizer_evaluations counts COBYLA objective calls of the final reported "
        "optimisation (not iterations); warm_start_evaluations counts the (gamma, beta) grid "
        "scan plus lower-depth passes; total_circuit_evaluations is their sum." if warm is not None
        else "optimizer_evaluations excludes the warm-start grid scan performed in quantum.py; "
             "total circuit evaluations are higher.")
    penalty_derivation = getattr(qubo, "penalty_derivation", None)

    record = {
        "scenario": name,
        "policy": policy,
        "seed": seed,
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "model": {
            "n_binary": qubo.n, "penalty": qubo.penalty,
            "weights": dict(qubo.weights), "role_order": list(qubo.ordering),
            "penalty_bound": getattr(qubo, "penalty_bound", None),
            "ising_offset": getattr(ham, "offset", None),
            "penalty_derivation": penalty_derivation,
        },
        "quantum": {
            "ran_qiskit": ran,
            "best_feasible_bits": list(q_bits) if q_bits else None,
            "utility": u_q,
            "feasible_sample_fraction": frac,
            "shots": q("shots"), "qaoa_reps": q("reps"),
            "optimizer_iterations": q("optimizer_evaluations"),
            "elapsed_seconds": q("elapsed_seconds"),
            "breakdown": q_score,
            "status": None if not ran else ("feasible_found" if q_bits else "no_feasible_sample"),
            "best_sample_count": best["count"] if best else None,
            "distinct_bitstrings_sampled": len(ranking) if ran else None,
            "backend": q("backend"), "maxiter": q("maxiter"),
            "circuit_depth": q("circuit_depth"),
            "optimal_params": q("optimal_params"),
            "selection_rule": SELECTION_RULE,
            "sample_ranking": ranking if ran else None,
            "shots_note": SHOTS_NOTE,
            "evaluation_counts": evals,
            "diagnostics": diag,
        },
        "exact": {
            "best_bits": list(e_bits) if e_bits else None,
            "utility": u_e,
            "enumerated_states": exact.enumerated_states,
            "elapsed_seconds": exact.elapsed_seconds,
            "breakdown": e_score,
            "feasible_states": exact.feasible_states,
            "infeasible_states": exact.infeasible_states,
        },
        "comparison": {"absolute_gap": abs_gap, "relative_gap_pct": rel_gap,
                       "interpretation": interpretation,
                       "no_speedup_note": NO_SPEEDUP_NOTE, "timing_note": TIMING_NOTE},
        "constraint_checks": checks,
        "software_versions": software_versions(),
        "notes": notes,
        "scenario_meta": scenario.to_dict(),
        "output_file": None,
    }
    return record


def _write(record: dict, out_dir: str | Path) -> None:
    folder = _runs_dir(out_dir)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / run_filename(record["scenario"], record["policy"], record["seed"])
    try:
        record["output_file"] = path.relative_to(ROOT).as_posix()
    except ValueError:
        record["output_file"] = path.name  # never store an absolute path
    path.write_text(json.dumps(record, indent=2, default=float), encoding="utf-8")


def run_scenario(name: str, policy: str, seed: int = 42, *, shots: int = 1024,
                 reps: int = 1, maxiter: int = 80, write: bool = True,
                 out_dir: str | Path = "artifacts/runs",
                 solver_modules: dict[str, Any] | None = None) -> dict:
    """Load, build QUBO/Hamiltonian, solve exact and QAOA, judge samples, save JSON.

    For relay_failure the base scenario is also solved here (same policy, seed and
    settings; not written to disk) to build the additive ``healing`` key. That is
    a second real QAOA run.
    """
    mods = _load_solvers(solver_modules)
    record = _solve(name, policy, seed, shots, reps, maxiter, mods)
    if name == "relay_failure":
        base_rec = _solve("base", policy, seed, shots, reps, maxiter, mods)
        record["healing"] = build_healing(base_rec, record)
    if write:
        _write(record, out_dir)
    return record


# ---- P1: self-healing (relay_failure) -----------------------------------------

def roles_of(bits) -> list[str] | None:
    """Canonical role labels of the active bits."""
    return None if bits is None else [k for k, b in zip(ROLE_KEYS, bits) if b]


def _stage(bits, score: dict | None) -> dict:
    return {"bits": list(bits) if bits is not None else None, "roles": roles_of(bits),
            "breakdown": score,
            "connected_teams": score["connected_teams"] if score else None}


def build_healing(base_rec: dict, fail_rec: dict, failed_drone: str = "B") -> dict:
    """Before (base plan) -> immediately after failure (no re-plan) -> replanned.

    Done separately for the quantum and the exact branch; never mixes them.
    """
    fail_sc = load_scenario(fail_rec["scenario"], fail_rec["policy"])
    out: dict[str, Any] = {
        "failed_drone": failed_drone,
        "before_source": (f"base run solved in this call (policy={base_rec['policy']}, "
                          f"seed={base_rec['seed']}, timestamp={base_rec['timestamp']})"),
        "before_run": {"quantum": {k: base_rec["quantum"][k] for k in
                                   ("ran_qiskit", "status", "feasible_sample_fraction",
                                    "shots", "qaoa_reps", "optimizer_iterations")},
                       "exact": {"utility": base_rec["exact"]["utility"]},
                       "comparison": base_rec["comparison"]},
        "before": {}, "immediately_after_failure": {}, "replanned": {},
        "lost_mission_utility": {}, "recovered_connectivity": {}, "notes": [],
    }
    for branch, key in (("quantum", "best_feasible_bits"), ("exact", "best_bits")):
        b_bits, r_bits = base_rec[branch][key], fail_rec[branch][key]
        out["before"][branch] = _stage(b_bits, base_rec[branch]["breakdown"])
        out["replanned"][branch] = _stage(r_bits, fail_rec[branch]["breakdown"])
        if b_bits is None:
            for stage in ("immediately_after_failure", "lost_mission_utility",
                          "recovered_connectivity"):
                out[stage][branch] = None
            out["notes"].append(f"{branch}: no feasible base plan; failure impact undefined.")
            continue
        d = score_degraded(tuple(b_bits), failed_drone, fail_sc)
        out["immediately_after_failure"][branch] = {
            "bits": d["bits"], "roles": roles_of(d["bits"]),
            "lost_roles": [ROLE_KEYS[i] for i in d["lost_roles"]],
            "connectivity_lost": d["connectivity_lost"],
            "connected_teams": d["connected_teams"],
            "breakdown": {k: d[k] for k in ("mission_score", "energy_penalty",
                                            "connectivity_bonus", "total_utility",
                                            "connected_teams", "feasible")}}
        out["lost_mission_utility"][branch] = (
            d["mission_score"] < base_rec[branch]["breakdown"]["mission_score"])
        replan_conn = out["replanned"][branch]["connected_teams"]
        # True only if the failure cut connectivity AND the re-plan restores it.
        out["recovered_connectivity"][branch] = bool(
            d["connectivity_lost"] and replan_conn is not None
            and replan_conn >= out["before"][branch]["connected_teams"])
        if not d["connectivity_lost"]:
            out["notes"].append(f"{branch}: failure did not cut connectivity; "
                                "recovered_connectivity is false by definition.")
        if r_bits is None:
            out["notes"].append(f"{branch}: no feasible replanned plan.")
    return out


# ---- P2: policy sweep ------------------------------------------------------------

def _best_u(scenario, connected: int) -> float | None:
    """Best true utility among feasible plans with the given connected_teams (exhaustive)."""
    from itertools import product
    us = [s["total_utility"] for b in product((0, 1), repeat=N_BITS) if is_feasible(b, scenario)
          for s in [score_feasible(b, scenario)] if s["connected_teams"] == connected]
    return max(us) if us else None


def unchanged_reason(name: str, pol_a: str, pol_b: str, bits) -> str:
    """One-line reason, computed from the data, why two presets share an exact plan."""
    conn = score_feasible(tuple(bits), load_scenario(name, pol_a))["connected_teams"]
    parts, stays_lower = [], True
    for p in (pol_a, pol_b):
        s = load_scenario(name, p)
        alt = _best_u(s, 1 - conn)
        u = score_feasible(tuple(bits), s)["total_utility"]
        stays_lower = stays_lower and (alt is None or alt < u)
        parts.append(f"W={s.relay_weight:g}: plan U={u:g} vs best "
                     f"connected_teams={1 - conn} plan U={'none' if alt is None else f'{alt:g}'}")
    why = (f"W shifts all such plans equally and the best plan with connected_teams={1 - conn} "
           "stays lower" if stays_lower else
           f"a plan with connected_teams={1 - conn} scores higher under at least one preset, "
           "so the shared plan is not explained by W alone")
    return (f"plan unchanged ({pol_a}, {pol_b}): the plan has connected_teams={conn}; "
            f"{why} ({'; '.join(parts)})")


def _vs(bits, ref_bits, scenario) -> dict:
    """Roles and mission value forfeited compared with the balanced plan."""
    if bits is None or ref_bits is None:
        return {"forfeited_roles": None, "added_roles": None, "mission_score_delta": None}
    a, r = set(roles_of(bits)), set(roles_of(ref_bits))
    ms = score_feasible(tuple(bits), scenario)["mission_score"]
    ms_ref = score_feasible(tuple(ref_bits), scenario)["mission_score"]
    return {"forfeited_roles": sorted(r - a, key=ROLE_KEYS.index),
            "added_roles": sorted(a - r, key=ROLE_KEYS.index),
            "mission_score_delta": ms - ms_ref}


def run_policy_sweep(name: str, seed: int = 42, **kw) -> dict:
    """Real solve per preset (each written as a normal run file) plus a comparison.

    Raw total utility is not compared across presets (W differs); the forfeited
    value uses mission_score, which does not depend on W.
    """
    records = {p: run_scenario(name, p, seed, **kw) for p in POLICIES}
    return summarize_sweep(name, seed, records)


def summarize_sweep(name: str, seed: int, records: dict[str, dict]) -> dict:
    """Comparison rows from per-policy run records (pure; no solver calls)."""
    keys =(("quantum", "best_feasible_bits"), ("exact", "best_bits"))
    ref = {br: records["balanced"][br][k] for br, k in keys}
    sc = load_scenario(name, "balanced")
    rows = []
    for p in POLICIES:
        r = records[p]
        row: dict[str, Any] = {"policy": p, "W": r["scenario_meta"]["relay_weight"]}
        for br, k in keys:
            bits, bd = r[br][k], r[br]["breakdown"]
            row[br] = {"bits": bits, "roles": roles_of(bits), "utility": r[br]["utility"],
                       "connected_teams": bd["connected_teams"] if bd else None,
                       **_vs(bits, ref[br], sc)}
        row["quantum_matches_exact"] = row["quantum"]["bits"] == row["exact"]["bits"]
        rows.append(row)
    unchanged = []
    for br, k in keys:
        for i, a in enumerate(POLICIES):
            for b in POLICIES[i + 1:]:
                pa = records[a][br][k]
                if pa is not None and pa == records[b][br][k]:
                    unchanged.append({"branch": br, "policies": [a, b],
                                      "reason": unchanged_reason(name, a, b, pa)})
    return {"scenario": name, "seed": seed, "records": records, "rows": rows,
            "unchanged": unchanged}
