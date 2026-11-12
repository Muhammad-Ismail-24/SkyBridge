# Completion Report — SkyBridge
- As of (date/time + timezone): 2026-11-12 ~19:00 PKT (+05:00); machine clock shows 13:58 GMT.
- Owner / agent: Ismail (simulation & systems lead), Claude Code (Sonnet 5.5). Zaheen's Z1 to Z3 rows are kept from his earlier report (17:56 PKT).
- Branch / commit SHA: `feat/ismail-simulation`. Code commits `fe5a2c4`, `11f361c`, `7df35a5`, `e1b31da` on top of `bcc1723`; the commit that adds this report is the branch tip (see the final summary for its SHA).

## Completed and evidenced
| Requirement / feature | Files changed | Verification command | Actual outcome |
|---|---|---|---|
| Z1 QUBO from scenario data (6 conflict pairs, battery + failure masks, relay reward) | `src/model.py` (Zaheen) | `pytest tests/test_model.py -q` | PASS (full suite below) |
| Z1 Penalty from an explicit single-flip bound; Ising mapping; 256-state energy equivalence; bit order | `src/model.py` (Zaheen) | same | PASS. Max abs error 0.0 over 256 states |
| Z2 Real Qiskit QAOA (`qaoa_ansatz`, StatevectorEstimator objective, COBYLA, StatevectorSampler) | `src/quantum.py` (Zaheen) | evidence in `artifacts/runs/*.json` | `ran_qiskit` true in all five run files |
| Z3 Independent exact 256-state baseline | `src/baseline.py` (Zaheen) | `pytest tests/test_exact.py -q` | PASS |
| **P0-A** drone-to-role assignment under hard constraints (one role per drone, valley slot, payload, battery `<=` reserve, disabled drones). `is_feasible` re-derives everything from raw fields and does not import `src/model.py` | `src/scenario.py`, `src/evaluate.py`, `tests/test_constraints.py` | `pytest tests/test_constraints.py -q` | DONE. 256-state independent brute force (hand-coded in the test) matches `is_feasible` and `score_feasible` for base, relay_failure (balanced, mission_first, coverage_first) and shadow_block (all three policies) |
| **P0-B** two-hop connectivity `connected_T = x0 * (l_B*x2 + l_C*x4)`, also requiring BASE-HILL. A missing link removes the bonus only; it does not make a plan infeasible | `src/network.py`, `src/scenario.py` | `pytest tests/test_network.py -q` | DONE. `connected_T`, `valley_link_flags`, `relay_pairs` and the QUBO reward terms agree on all 256 states of all 9 scenario × policy instances (checked in the review and by `test_cross_*`) |
| **P0-C** QAOA and exact comparison written to JSON: `run.py` / `src/pipeline.py` judge samples with `is_feasible`/`score_feasible`, never fall back to the exact answer, and compute the gap with one scorer | `src/pipeline.py`, `run.py`, `tests/test_pipeline.py` | `python run.py --scenario base --policy balanced --seed 42` | DONE. See Results |
| **P1** self-healing (`relay_failure`): the `healing` key holds before / immediately-after-failure (no re-plan) / replanned, separately for the quantum and exact branches | `src/pipeline.py`, `src/evaluate.py` (`score_degraded`) | `python run.py --scenario relay_failure --policy balanced --seed 42` | DONE. Connectivity lost at failure, recovered by re-plan (A_H + C_V + D_Delivery, U = 24.5) in both branches |
| **P2** policy presets (W = 3 / 22 / 35) with real re-solves and a comparison table (`run_policy_sweep`, `--policy-sweep`) | `src/pipeline.py`, `run.py` | files `base__mission_first__seed42.json`, `base.json`, `base__coverage_first__seed42.json` | DONE (solver side and CLI). mission_first drops the relay (U = 18.25); balanced and coverage_first keep it |
| **P3** `shadow_block`: base with the HILL-VALLEY_B edge cut; the QUBO reward terms, scoring and `relay_pairs` change together | `src/scenario.py`, `artifacts/runs/shadow_block.json` | `python run.py --scenario shadow_block --policy balanced --seed 42` | DONE for scoring/solver. The map drawing is Sufiyan's |
| Review fix: loader rejects roles out of canonical order, naming the index (finding 10) | `src/scenario.py`, `tests/test_constraints.py` | `test_swapped_role_order_rejected` | PASS |
| Review fix: additive run-record keys `quantum.diagnostics`, `quantum.shots_note`, `quantum.evaluation_counts`, `comparison.interpretation`, `comparison.no_speedup_note`, `comparison.timing_note`, `model.penalty_derivation`, scipy and `qiskit_algorithms_used` in `software_versions`; repo-relative `output_file` (blocker 3, items 7, 8, 9, 15). No existing key was renamed or removed | `src/pipeline.py`, `tests/test_pipeline.py` | `pytest tests/test_pipeline.py -q` | PASS (hand-computed example in `test_fake_logic_only_diagnostics_values_by_hand`) |
| Review fix: `run.py --from-saved` prints one-line errors with exit code 2 for a missing file, invalid JSON or a missing key, and prints `LOADED FROM SAVED FILE <path> (not a new run)`; the summary shows the diagnostics (item 14) | `run.py` | `test_run_cli_*` | PASS |
| Review fix: stale files removed (`policy_coverage.json`, `policy_mission.json`); `shadow_block.json` regenerated; all five run files regenerated through `run.py` (blocker 2) | `artifacts/runs/` | see Results | DONE |
| Review fix: `requirements.txt` pinned to the Python 3.11.9 environment (blocker 1) | `requirements.txt` | clean clone, below | DONE. Installs on Python 3.11.9 |
| Review fix: test gaps (item 11): `shadow_block` added to `CROSS_CASES`; `coverage_first` goldens (base 42.5, relay_failure 37.5, both matched the code with no discrepancy); independent brute force for `shadow_block` | `tests/test_pipeline.py`, `tests/test_constraints.py` | same | PASS |

## Results measured (link actual artifacts)
Settings for every run: p = 1, 1024 shots, seed 42, COBYLA maxiter 80, `qiskit.primitives.StatevectorSampler`, Python 3.11.9, qiskit 2.6.2, numpy 2.4.6, scipy 1.17.1. All data are synthetic and illustrative. Every run was produced by `run.py`; `ran_qiskit` is true in all five files; each quantum plan passes `is_feasible`; each gap equals exact minus quantum utility from the same scorer (rechecked after regeneration).

| Artifact | Scenario / policy (W) | Penalty P (bound) | Quantum best feasible → U | Exact best → U | Gap | Feasible shot fraction (uniform) | Optimum frequency (uniform 0.0039) | Optimum rank by count | Most frequent sample (U) |
|---|---|---|---|---|---|---|---|---|---|
| `artifacts/runs/base.json` | base / balanced (22) | 45 (44) | `10100110` → 29.5 | `10100110` → 29.5 | 0.0 | 0.8506 (0.2461) | 0.0127 | 30 | `10001001` (23.25) |
| `artifacts/runs/relay_failure.json` | relay_failure / balanced (22) | 45 (44) | `10001010` → 24.5 | `10001010` → 24.5 | 0.0 | 0.6309 (0.1055) | 0.0225 | 14 | `10000000` (-1.0) |
| `artifacts/runs/shadow_block.json` | shadow_block / balanced (22) | 23 (22) | `10011001` → 27.0 | `10011001` → 27.0 | 0.0 | 0.8184 (0.2461) | 0.0195 | 7 | `10001000` (20.5) |
| `artifacts/runs/base__mission_first__seed42.json` | base / mission_first (3) | 7.5 (6.5) | `01010101` → 18.25 | `01010101` → 18.25 | 0.0 | 0.7295 (0.2461) | 0.0479 | 2 | `01000110` (15.75) |
| `artifacts/runs/base__coverage_first__seed42.json` | base / coverage_first (35) | 71 (70) | `10100110` → 42.5 | `10100110` → 42.5 | 0.0 | 0.8516 (0.2461) | 0.0176 | 16 | `01000000` (6.5) |

(Bit strings are canonical x0..x7 = A_H, A_N, B_V, B_Delivery, C_V, C_E, D_Delivery, D_S, not Qiskit-printed strings.)

Reproducibility: the regenerated files reproduced the previously saved best bits, optimal parameters and full sample lists exactly (same seed) for all four configurations that existed before; `shadow_block.json` matches the 18:23 run too. Elapsed times differ between runs (about 1.0 to 1.5 s now versus about 1.0 to 2.3 s before).

P1 (`relay_failure.json`, key `healing`), both branches identical: before (base, solved in the same call) A_H, B_V, C_E, D_Delivery, U = 29.5, connected 1; immediately after B fails (no re-plan) A_H, C_E, D_Delivery, U = 8.25, connected 0; replanned A_H, C_V, D_Delivery, U = 24.5, connected 1. `recovered_connectivity` is true for both. The relay_failure run therefore executes two QAOA solves.

**Honest interpretation of gap 0.** The quantum plan is the best *feasible* bitstring (by true utility) among all 1024 shots, not the most frequent one. Uniform random sampling would also contain the exact optimum in 1 - (255/256)^1024 = 98.2% of runs, so a zero gap is **not** evidence that QAOA solved the problem and is **not** a quantum advantage. In every run the most frequent sample was not the optimum (in `relay_failure.json` it is A_H alone, U = -1.0). What QAOA p = 1 does show is bias: the feasible shot fraction is 3.0x to 6.0x the uniform fraction, and the optimum frequency is 3.2x to 12x the uniform 1/256, but the optimum is only 2nd to 30th by count. Each run file now carries this evidence (`quantum.diagnostics`) and the wording (`comparison.interpretation`, `comparison.no_speedup_note`). Exact enumeration of 256 states takes about 0.002 s; the quantum elapsed time includes a warm-start grid scan and a metadata-only transpile, so the timings are not comparable (`comparison.timing_note`).

Earlier extra experiments (reps = 2, reps = 2 with maxiter 160, depth sweep, seed sweep) were run outside the repo or by Zaheen's driver and are not repeated here. Their conclusion stands: more depth raises feasibility and P(optimum) modestly (for example p = 2 reaches about 0.97 feasible fraction and 0.0195 P(optimum)) but never concentrates on the optimum. Zaheen's driver files (2048 shots, test-only evaluator) were deleted because they were not produced by `run.py`.

## Tests run (command, pass/fail counts, logs)
- Baseline before this task (Windows, `.venv`, Python 3.11.9): `.venv/Scripts/python.exe -m pytest -q` → **151 passed**.
- After the changes: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_network.py tests/test_constraints.py tests/test_pipeline.py` → **134 passed**, 0 failed.
- Full suite on the committed code: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider` → **182 passed**, 0 failed (includes Zaheen's `test_model.py` and `test_exact.py`).
- **Clean-clone proof** (commit `e1b31da`): `git clone . <scratch>/sb_clean`; `py -3.11 -m venv <scratch>/sb_venv2`; `pip install -r requirements.txt` → exit 0 (Python 3.11.9; qiskit 2.6.2, numpy 2.4.6, scipy 1.17.1, rustworkx 0.18.1, pytest 9.2.0, streamlit 1.67.0, python-docx 1.2.0); pytest on my three files → **134 passed in 6.57 s**; `python run.py --scenario base --policy balanced --seed 42 --no-write` → exit 0, `ran_qiskit` true, best bits `10100110`, U = 29.5, exact `10100110`, U = 29.5, gap 0.0. This equals the committed `artifacts/runs/base.json`.
- Real `run.py` runs in this task: 7 (five artifact runs, of which `relay_failure` also solves base once, so 6 QAOA solves, plus the clean-clone `--no-write` run).
- Structure check. `scripts/verify_structure.py` and `.skybridge-phase` do not exist on this branch (they are on Sufiyan's branch); I ran the checker from `origin/feature/sufiyan-dashboard-qa` unmodified against this tree: `python verify_structure.py --phase tracked --strict --root .` → **FAIL** (no `.skybridge-phase`); `--phase implementation --strict` → **FAIL**: missing `.skybridge-phase`, `scripts/`, `artifacts/figures/`, `report/`, `.github/`, `scripts/verify_structure.py`, `scripts/bootstrap_structure.py`, `.github/workflows/structure.yml`, `README.md`, and "Unexpected top-level entry: 'CLAUDE.md'". All of these are other owners' files or come with Sufiyan's branch; none concerns my files (`src/*`, `run.py`, `data/*.json`, tests, `artifacts/runs/*.json`, `requirements.txt` produced no violations). `CLAUDE.md` is tracked on this branch but is not in the checker's `TOP_ALLOWED`; see the Sufiyan handoff.

## Known defects and unresolved dependencies
- `optimizer_iterations` in run files is the COBYLA function-evaluation count of the final optimisation (31 to 39), not iterations, and excludes the 144-point warm-start grid scan. `quantum.evaluation_counts` now reports `warm_start_evaluations` = 144 (read from `QuantumResult`) and `total_circuit_evaluations` (for example 176 for `base.json`). The proper fix is in quantum.py (Zaheen, below).
- `shots` applies to the final sampling only; the optimisation loop uses the exact `StatevectorEstimator` (stated in `quantum.shots_note`).
- `ran_qiskit` in the pipeline is read from `QuantumResult.ran_qiskit`, which is a literal `True` in `quantum.py` (Zaheen item 12).
- The relay_failure run solves base again (two QAOA solves) instead of reading `base.json`.
- Sufiyan's branch adds its own `tests/test_pipeline.py` and `README.md`; merging will conflict in `tests/test_pipeline.py` (keep both sections). His README says Python 3.12 and 3.12 pins; `requirements.txt` here carries the 3.11.9 pins.
- `scripts/verify_structure.py` fails on this branch for the reasons above until Sufiyan's branch is merged.
- No other seeds were run; every result here is seed 42, so it says nothing about run-to-run variation of QAOA (the optimiser angles are seed-independent because the Estimator is exact; only the sampler is seeded).

## Not implemented / deferred features
- Map/dashboard drawing for P3 (Sufiyan), README, DOCX report, video, CI (others).
- P4 to P7: deferred.
- Multi-seed reporting at the chosen setting.

## Assumptions and limitations
- All scenario data (utilities, energies, batteries, weights, links) are synthetic and illustrative. The link matrix is an illustrative terrain obstruction, not an RF prediction.
- A missing radio link does not make a plan infeasible; it only removes the connectivity bonus (`connected_T = x0 * (l_B*x2 + l_C*x4)`). The formula is exact for this two-relay topology only.
- Battery rule: `e_i + reserve <= battery[drone]` (reserve 15). `relay_failure` disables drone B entirely (x2 = x3 = 0). `shadow_block` is base with the HILL-VALLEY_B edge removed in code.
- The penalty is the derived single-flip bound plus margin 1 (`quantum`-independent proof in `src/model.py`), smaller than the example in architecture.md §4.3; it is logged in every run (`model.penalty`, `model.penalty_bound`, `model.penalty_derivation`). For W = 35 it is 71 (base, relay_failure) and 36 (shadow_block); all nine scenario × policy instances were checked exhaustively: energy equals minus utility on all feasible states and the unique minimiser is the unique feasible optimum.
- `out_dir` must resolve to a folder named `artifacts/runs`; `output_file` is repo-relative POSIX (filename only if the folder were outside the repo).
- Toy 8-variable instance on a local statevector simulator; no real hardware; no quantum speedup is claimed.

## Next owner / actionable handoff
### Handoff to Zaheen (`src/quantum.py`; I did not edit it)
- **Item 4, evaluation count** (`quantum.py:211-218`, `:293-294`, `to_dict` at `:117`): the reported `optimizer_evaluations = int(res.nfev)` counts only the final COBYLA call; the 144-point grid scan (`warm_evals`) is separate. Add a field `total_circuit_evaluations = warm_evals + int(res.nfev)` and rename the output key `optimizer_iterations` to `optimizer_function_evaluations` (keep the old key as an alias for the dashboard). Why: `base.json` shows 32 but 176 circuit evaluations ran. The pipeline already reads `warm_start_evaluations` and computes the total itself.
- **Item 6, timing** (`quantum.py:185`, `:302`, `:267-272`): `elapsed_seconds` bundles the grid scan, COBYLA, sampling and a metadata-only `transpile`. Add `optimization_seconds`, `sampling_seconds` and `transpile_seconds` (time each block with `perf_counter`), and keep `elapsed_seconds` as the total. Why: the transpile result is never executed, and exact is about 700x faster, so a single number invites a misleading comparison.
- **Item 12, `ran_qiskit` literal** (`quantum.py:276`): replace `ran_qiskit=True` with a value derived from evidence, for example `ran_qiskit=bool(counts) and sum(counts.values()) == int(shots)`, computed after `job.result()`. Why: today it is true by construction rather than by observation.
- **Item 13, solver-to-solver import** (`quantum.py:40`): `from src.baseline import FeasibleFn, ScoreFn, resolve_evaluator, total_utility` makes the quantum branch import the exact-solver module. Move those four helpers into a neutral place (`src/evaluate.py` is mine, so either define `FeasibleFn`/`ScoreFn`/`total_utility` locally in `quantum.py` and import `is_feasible`/`score_feasible` from `src.evaluate`, or ask me to add a small `types`-only helper there). Why: removes any appearance that the quantum path depends on `baseline.py`. It never calls `solve_exact` today.

### Handoff to Sufiyan
- Read `artifacts/runs/`: `base.json`, `relay_failure.json` (has `healing`), `shadow_block.json`, `base__mission_first__seed42.json`, `base__coverage_first__seed42.json`. Delete `policy_coverage.json` and `policy_mission.json` if they exist on your branch; they were not produced by `run.py`, contradict the new files, and your globbing dashboard test will fail on them.
- New keys to show in the UI and report: `quantum.diagnostics` (`selection_method`, `most_frequent_sample`, `optimum_sample_frequency`, `optimum_sample_count`, `uniform_baseline`), `comparison.interpretation`, `comparison.no_speedup_note`, `comparison.timing_note`, `quantum.shots_note`, `quantum.evaluation_counts`, `model.penalty_derivation`. Show the interpretation next to any gap 0 so it is not read as "QAOA solved it". The old keys, including `quantum_matches_exact` and the two `*_rechecked` check names, are unchanged.
- I added `requirements.txt` (taken from your branch) and changed only `numpy==2.4.6` and `scipy==1.17.1`, because the 3.12 pins (`2.5.4` and `1.18.1`) have no Python 3.11 wheels. It installs on 3.11.9 (verified in a clean clone). Please keep the README and CI on one Python version.
- `CLAUDE.md` is tracked at the top level but `scripts/verify_structure.py` does not list it in `TOP_ALLOWED`; either add it there or move it into a canonical location (I did not touch the checker).
- Merge note: `tests/test_pipeline.py` will conflict; keep both sections.

## Source attribution (if any code reused)
- No third-party code was copied. Uses Qiskit public APIs (`qaoa_ansatz`, `SparsePauliOp`, `StatevectorEstimator`, `StatevectorSampler`, `transpile`) and SciPy COBYLA (Zaheen's modules).
- The INTERP warm-start schedule follows Zhou, Wang, Choi, Pichler, Lukin, *Phys. Rev. X* 10, 021067 (2020); reimplemented by Zaheen, not copied.
