"""SkyBridge headless CLI: run one scenario through the real pipeline.

Examples:
  python run.py --scenario base --policy balanced --seed 42
  python run.py --scenario relay_failure --policy balanced --seed 42   # + self-healing stages
  python run.py --policy-sweep --scenario base --seed 42               # 3 presets, 3 solves
  python run.py --policy-sweep --scenario base --seed 42 --from-saved  # table only, no solve
All scenario data are synthetic and illustrative.
"""
from __future__ import annotations

import argparse
import sys

import json

from src.pipeline import ROOT, run_filename, run_policy_sweep, run_scenario, summarize_sweep

RUNS = ROOT / "artifacts" / "runs"
from src.scenario import POLICIES, SCENARIOS

ORDER = ("A_H", "A_N", "B_V", "B_Delivery", "C_V", "C_E", "D_Delivery", "D_S")


def _plan(bits: list[int] | None) -> str:
    if bits is None:
        return "none"
    return "".join(map(str, bits)) + "  (" + ", ".join(k for k, b in zip(ORDER, bits) if b) + ")"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--scenario", choices=SCENARIOS, default="base")
    ap.add_argument("--policy", choices=POLICIES, default="balanced")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--shots", type=int, default=1024)
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--maxiter", type=int, default=80)
    ap.add_argument("--no-write", action="store_true", help="do not save the JSON record")
    ap.add_argument("--policy-sweep", action="store_true",
                    help="solve all three policy presets and print a comparison table")
    ap.add_argument("--from-saved", action="store_true",
                    help="with --policy-sweep: rebuild the table from saved run files (no solve)")
    a = ap.parse_args(argv)
    kw = dict(shots=a.shots, reps=a.reps, maxiter=a.maxiter, write=not a.no_write)

    try:
        if a.policy_sweep and a.from_saved:
            recs = {}
            for p in POLICIES:
                path = RUNS / run_filename(a.scenario, p, a.seed)
                print(f"LOADED FROM SAVED FILE {path} (not a new run)")
                recs[p] = json.loads(path.read_text(encoding="utf-8"))
            print_sweep(summarize_sweep(a.scenario, a.seed, recs))
            return 0
        if a.policy_sweep:
            print_sweep(run_policy_sweep(a.scenario, a.seed, **kw))
            return 0
        r = run_scenario(a.scenario, a.policy, a.seed, **kw)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(f"error: saved run file not found: {exc.filename}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"error: saved run file is invalid JSON ({exc.msg} at line {exc.lineno})",
              file=sys.stderr)
        return 2
    except KeyError as exc:
        print(f"error: saved run file is missing key {exc}", file=sys.stderr)
        return 2
    print_run(r)
    if "healing" in r:
        print_healing(r["healing"])
    return 0


def _roles(roles: list[str] | None) -> str:
    return "none" if roles is None else (", ".join(roles) or "(idle)")


def print_healing(h: dict) -> None:
    """P1: the three self-healing stages, quantum and exact shown separately."""
    print(f"\nSELF-HEALING  failed drone {h['failed_drone']}  ({h['before_source']})")
    for br in ("quantum", "exact"):
        b, d, r = h["before"][br], h["immediately_after_failure"][br], h["replanned"][br]
        u = lambda st: st["breakdown"]["total_utility"] if st and st["breakdown"] else None
        print(f"[{br.upper()}]")
        print(f"  1 before                     {_roles(b['roles'])}  U={u(b)} "
              f"connected_teams={b['connected_teams']}")
        if d is None:
            print("  2 immediately after failure  undefined (no feasible base plan)")
        else:
            print(f"  2 immediately after failure  {_roles(d['roles'])}  U={u(d)} "
                  f"connected_teams={d['connected_teams']}  lost_roles={d['lost_roles']} "
                  f"connectivity_lost={d['connectivity_lost']}  (no re-optimisation)")
        print(f"  3 replanned                  {_roles(r['roles'])}  U={u(r)} "
              f"connected_teams={r['connected_teams']}")
        print(f"  lost_mission_utility={h['lost_mission_utility'][br]}  "
              f"recovered_connectivity={h['recovered_connectivity'][br]}")
    for n in h["notes"]:
        print(f"note:    {n}")


def print_sweep(sw: dict) -> None:
    """P2: comparison table across the three presets."""
    print(f"POLICY SWEEP  scenario={sw['scenario']} seed={sw['seed']}  "
          "(synthetic, illustrative; raw U is not comparable across W)")
    hdr = (f"{'policy':<15}{'W':>4}  {'branch':<8}{'roles':<38}{'conn':>5}{'U':>8}  "
           f"{'forfeited vs balanced':<26}{'mission d':>9}")
    print(hdr)
    print("-" * len(hdr))
    for row in sw["rows"]:
        for br in ("quantum", "exact"):
            x = row[br]
            forf = "n/a" if x["forfeited_roles"] is None else (", ".join(x["forfeited_roles"]) or "-")
            print(f"{row['policy'] if br == 'quantum' else '':<15}"
                  f"{row['W'] if br == 'quantum' else '':>4}  {br:<8}{_roles(x['roles']):<38}"
                  f"{str(x['connected_teams']):>5}{str(x['utility']):>8}  {forf:<26}"
                  f"{str(x['mission_score_delta']):>9}")
        print(f"{'':<21}quantum matches exact: {row['quantum_matches_exact']}")
    for u in sw["unchanged"]:
        print(f"[{u['branch']}] {u['reason']}")
    for p, r in sw["records"].items():
        print(f"saved:   {r['output_file'] or '(not written)'}")


def print_run(r: dict) -> None:
    q, e, c = r["quantum"], r["exact"], r["comparison"]
    print(f"SkyBridge run  scenario={r['scenario']} policy={r['policy']} seed={r['seed']}"
          f"  (synthetic, illustrative data)")
    print(f"model    n_binary={r['model']['n_binary']} penalty={r['model']['penalty']} "
          f"weights={r['model']['weights']}")
    print(f"QUANTUM  ran_qiskit={q['ran_qiskit']} status={q['status']} backend={q['backend']}")
    print(f"         shots={q['shots']} reps={q['qaoa_reps']} "
          f"optimizer_iterations={q['optimizer_iterations']} elapsed_s={q['elapsed_seconds']}")
    print(f"         feasible_sample_fraction={q['feasible_sample_fraction']} "
          f"distinct_bitstrings={q['distinct_bitstrings_sampled']}")
    print(f"         best_feasible={_plan(q['best_feasible_bits'])}  U={q['utility']}")
    print(f"EXACT    best={_plan(e['best_bits'])}  U={e['utility']}")
    print(f"         enumerated={e['enumerated_states']} feasible={e['feasible_states']} "
          f"infeasible={e['infeasible_states']} elapsed_s={e['elapsed_seconds']}")
    print(f"GAP      absolute={c['absolute_gap']} relative_pct={c['relative_gap_pct']}")
    d = q.get("diagnostics")
    if d:
        mf, ub = d["most_frequent_sample"], d["uniform_baseline"]
        print(f"DIAG     most frequent sample {mf['bits']} count={mf['count']} "
              f"feasible={mf['feasible']} utility={mf['utility_or_null']}")
        print(f"         optimum frequency {d['optimum_sample_frequency']} vs uniform per-shot "
              f"rate {ub['p_hit_optimum_per_shot']:.6f}; uniform sampling would contain the "
              f"optimum in {100 * ub['p_hit_optimum_within_shots']:.1f}% of runs")
    if c.get("interpretation"):
        print(f"         {c['interpretation']}")
    if c.get("no_speedup_note"):
        print(f"         {c['no_speedup_note']}")
    failed = [k for k, v in r["constraint_checks"].items() if v is False]
    print(f"CHECKS   {'all true' if not failed else 'FAILED: ' + ', '.join(failed)}")
    for n in r["notes"]:
        print(f"note:    {n}")
    print(f"saved:   {r['output_file'] or '(not written)'}")


if __name__ == "__main__":
    sys.exit(main())
