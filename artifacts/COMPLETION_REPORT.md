# Completion Report — SkyBridge
- As of (date/time + timezone): 2026-11-12 17:56 PKT
- Owner / agent: Zaheen (quantum & optimisation lead), implemented with Claude Code (Opus 5.5)
- Branch / commit SHA: `main`; this report is part of the first commit (SHA is in `git log`, not repeated here so the file doesn't refer to itself)

## Completed and evidenced
| Requirement / feature | Files changed | Verification command | Actual outcome |
|---|---|---|---|
| Z1 QUBO from scenario data (6 conflict pairs, battery + failure masks, relay reward) | `src/model.py` | `pytest tests/test_model.py -q` | PASS. Coefficients match hand derivation (`test_base_qubo_coefficients_match_hand_derivation`) |
| Z1 Penalty from an explicit bound | `src/model.py` (`penalty_lower_bound`) | same | PASS. Bound B = 44 (base/balanced); P = B + 1 = 45. A single-flip improvement is verified for **every** infeasible state |
| Z1→Ising mapping, `SparsePauliOp`, separate offset | `src/model.py` (`build_hamiltonian`) | same | PASS. **256-state max abs error = 0.0** (terms and Qiskit matrix diagonal) for 6 scenario variants; tolerance 1e-8 |
| Bit order / endianness (only x0, only x7, Qiskit Statevector labels) | `src/model.py` | same | PASS |
| Z2 Real Qiskit QAOA (`qaoa_ansatz`, StatevectorEstimator objective, COBYLA, StatevectorSampler) | `src/quantum.py` | `pytest tests/test_model.py -q` + evidence run | PASS. 8 qubits, p=1, 2048 shots, seed 42. Results in `artifacts/runs/*.json` |
| Z2 Decoding + feasible selection using the original checker | `src/quantum.py` (`select_feasible`) | same | PASS. Infeasible samples are rejected, never repaired; `no_feasible_sample` status is tested |
| Z3 Independent exact 256-state baseline | `src/baseline.py` | `pytest tests/test_exact.py -q` | PASS. Enumerates 256 states; 63 feasible in base (matches the counting argument 81−9−9); 27 under B failure |
| Z3 Quantum vs exact gap (same true utility) | `src/baseline.py` (`compare_results`, `rank_of_utility`) | same | PASS. Zero denominator and missing quantum result are handled |
| P1 relay_failure re-solve (solver side) | evidence run | see results | Quantum and exact both pick A hill + **C backup valley** + D delivery, U = 24.5 |
| P2 policy presets (solver side) | evidence run | see results | mission_first drops the relay (U = 18.25); coverage_first keeps it (U = 42.5) |

**Combined test command:** `.venv/bin/python -m pytest tests/test_model.py tests/test_exact.py -q` → `48 passed in 2.52s`.

## Results measured (link actual artifacts)
Settings for every row: p=1, shots=2048, seed=42, COBYLA maxiter=80 after a 144-point (γ, β) grid warm start, StatevectorSampler. Circuit after transpile: depth 19, 16 CX. Utilities are synthetic.

| Scenario | Artifact | Exact best (U) | QAOA best feasible sample (U) | Gap | Feasible shot fraction | P(exact optimum) in samples |
|---|---|---|---|---|---|---|
| base / balanced | `artifacts/runs/base.json` | `10100110` A_H,B_V,C_E,D_Delivery (29.5) | same (29.5) | 0.0 | 0.841 | 0.0156 |
| relay_failure / balanced | `artifacts/runs/relay_failure.json` | `10001010` A_H,C_V,D_Delivery (24.5) | same (24.5) | 0.0 | 0.623 | 0.0225 |
| base / mission_first (W=3) | `artifacts/runs/policy_mission.json` | `01010101` all recon/delivery (18.25) | same (18.25) | 0.0 | 0.730 | 0.0483 |
| base / coverage_first (W=35) | `artifacts/runs/policy_coverage.json` | `10100110` (42.5) | same (42.5) | 0.0 | 0.840 | 0.0146 |

(The bit strings above are canonical x0…x7, not Qiskit-printed strings.)

**Reference points for judging the quantum contribution:**
- Uniformly random bitstrings: feasible fraction 63/256 = 0.246 (base) and 27/256 = 0.105 (failure). P(optimum) = 1/256 = 0.0039.
- QAOA p=1 reaches 3.4×–5.9× the uniform feasible fraction and 3.7×–12× the uniform optimum probability.
- With 2048 shots, random sampling would also very likely contain the optimum somewhere. So "the best sample equals the optimum" is **not** evidence of quantum advantage on its own. The meaningful measures are the expected energy, the feasible fraction and P(optimum).
- Depth sweep, base, seed 42: expected QUBO energy −5.18 (p=1) → −10.64 (p=2) → −13.20 (p=3); P(opt) 0.016 → 0.021 → 0.030; feasible fraction 0.84 → 0.97 → 0.96. The ground-state energy is −29.5, so p≤3 stays far from concentrating on the optimum.
- Seed sweep at p=1 (seeds 42, 7, 2026): all three seeds give the same best feasible sample in every scenario. The optimised angles are seed-independent, because the Estimator is exact and only the sampler is seeded.

## Tests run (command, pass/fail counts, logs)
- `.venv/bin/python -m pytest tests/test_model.py tests/test_exact.py -q` → **48 passed**, 0 failed.
- Evidence run: the scratch driver (not committed) imports `src.model`, `src.quantum` and `src.baseline` and writes the four JSON files above. It ran to completion and printed the values in the table.
- `scripts/verify_structure.py` **not run: the file does not exist yet** (Sufiyan-owned).

## Known defects and unresolved dependencies
- **BLOCKED on Ismail:** `src/scenario.py`, `src/evaluate.py`, `src/network.py`, `src/pipeline.py` and `run.py` do not exist yet. Tests and evidence use `tests/reference_contract.py`, a **test-only** literal transcription of architecture.md §4. `tests/conftest.py` switches to Ismail's modules automatically once `src.scenario.load_scenario` and `src.evaluate.is_feasible/score_feasible` import.
- **Proposed G0 Scenario fields** (read only by `model.model_inputs_from_scenario`, so a different layout needs a change in that one function): `roles[i].{key, drone, utility, energy}` in canonical order, `battery`, `reserve`, `alpha`, `relay_reward` (W), `conflict_pairs`, `relay_pairs` (validated (hill, valley) index pairs from the adjacency matrix), `disabled_drones`. `score_feasible` must return `total_utility`.
- `solve_qaoa(qubo, ...)` has no scenario argument (per the contract), so feasibility ranking is a separate call: `select_feasible(result, scenario)`. The pipeline must call both.
- `artifacts/runs/*.json` were produced by the solver-evidence driver, not by `run_scenario`. Regenerate them via `python run.py ...` once the pipeline exists.
- No `requirements.txt` yet (Sufiyan-owned). Working versions are listed below.

## Not implemented / deferred features
- P3 ShadowMap UI and P4–P7: not in Zaheen's scope. The solver side of a blocked link is tested (`test_blocked_link_*`).
- `run.py`, the UI, the README, the DOCX report and CI are owned by others and were not touched.

## Assumptions and limitations
- **Penalty:** architecture.md §4.3 gives `P > Σ|c_i| + W + 1` (= 47.5) as an *example*. The implementation instead uses the derived single-flip bound `P > max_i(max(c_i,0) + Σ_j W_ij)`, which is provably sufficient and smaller (P = 45), so it squeezes the feasible energy spectrum less. Passing an explicit penalty at or below the bound raises an error.
- H_C is divided by its largest coefficient before building the ansatz. This rescales γ only; the reported expectations use the unscaled Hamiltonian plus the offset.
- Python 3.12.13 was used (the spec suggests 3.11; 3.11 is not installed on this Mac). Qiskit 2.6.2 does not need `qiskit-algorithms`, which is not used.
- The two-relay quadratic connectivity term is exact only for this topology. The model is a toy 8-variable instance, battery and RF are illustrative, there is no quantum speedup, and it is not deployable.

## Next owner / actionable handoff
- **Ismail:** implement `load_scenario`, `is_feasible` and `score_feasible` with the fields above, then `run_scenario`, which should call `build_qubo → solve_exact → solve_qaoa(seed=42, shots=2048, reps=1, maxiter=80) → select_feasible → compare_results` and serialise with `.to_dict()`. Run `pytest tests -q`; conftest will then use your modules.
- **Sufiyan:** `requirements.txt` pins: `qiskit==2.6.2 numpy==2.5.4 scipy==1.18.1 rustworkx==0.18.1 pytest==9.2.0` (Python 3.12). For report tables, read `artifacts/runs/*.json` keys `exact`, `quantum`, `comparison`, `experiments`.
- Reproduce: `python3.12 -m venv .venv && .venv/bin/pip install qiskit==2.6.2 numpy==2.5.4 scipy==1.18.1 pytest==9.2.0 && .venv/bin/python -m pytest tests/test_model.py tests/test_exact.py -q`

## Source attribution (if any code reused)
- No third-party code was copied. It uses Qiskit public APIs (`qaoa_ansatz`, `SparsePauliOp`, `StatevectorEstimator`, `StatevectorSampler`, `transpile`) and SciPy COBYLA.
- The INTERP warm-start schedule follows Zhou, Wang, Choi, Pichler, Lukin, *Phys. Rev. X* 10, 021067 (2020). It was reimplemented, not copied.

## Sufiyan scaffold milestone — 2026-11-12 18:03 PKT
- The starter ZIP's `skybridge/` contents were copied into the cloned repository root without replacing Zaheen's existing files. Existing `architecture.md`, `work_division.md`, and `.gitignore` were preserved.
- Added `.skybridge-phase`, GitHub Actions structure workflow, bootstrap/verifier scripts, canonical directory markers, and the package's architecture figure.
- `python scripts/bootstrap_structure.py` — PASS: canonical directories present.
- `python scripts/verify_structure.py --phase scaffold --strict` — PASS.
- `main` already contained Zaheen's solver commit `325893cc9b7c697fdd197147f4eca0ace11ec6e3`; this scaffold was prepared on `chore/skybridge-scaffold` to avoid overwriting that work.
- Next: push scaffold branch, verify remote, then start Sufiyan's feature branch. No new Qiskit measurement was made in this milestone.

## Sufiyan implementation milestone — 2026-11-12 18:15 PKT
- Branch: `feature/sufiyan-dashboard-qa` from pushed scaffold commit `6faee91f561d9ddf7a25bab2e1562eedb942118d`.
- Added `app.py`: reads saved JSON, validates eight-variable order and objective totals, shows four-drone assignments, solver comparison, provenance and truthful network-data pending state. It does not invent radio edges.
- Added `tests/test_pipeline.py`: validates four solver-evidence artifacts, the dashboard boundary and malformed input; a production CLI test is skipped until Ismail's `run.py` exists.
- Added `README.md`, `requirements.txt`, `scripts/generate_report.py`, `scripts/verify_submission.py`, and generated `report/SkyBridge_Hackathon_Report.docx` (embedded starter-package architecture figure; current measured solver-evidence table; production pipeline explicitly pending).
- `python -m pytest tests/test_pipeline.py -q -p no:cacheprovider` — PASS: 5 passed, 1 skipped.
- `python scripts/verify_structure.py --phase scaffold --strict` — PASS. The tracked phase remains scaffold because Ismail's required P0 files are absent.
- `python -m pytest tests -q -p no:cacheprovider` — FAIL at collection: this Windows Python 3.14 environment lacks Qiskit. Zaheen's report records 48 solver tests passing on a separate Python 3.12.13 environment; those tests were not reproduced here.
- `python scripts/verify_submission.py` — PENDING: missing production CLI/scenario/network/evaluator/pipeline and production-generated run JSON, so submission requirements are not yet met.
- Report structural check with python-docx 1.2.0: 28 paragraphs, 2 tables, 1 embedded image. Visual render unavailable: the packaged renderer needs `pdf2image` and a bundled LibreOffice runtime not present in this Windows environment.
- This machine has only Python 3.14.2. `python-docx==1.2.0` was installed into an external workspace dependency directory for report generation; Streamlit and the solver stack have not been installed or exercised here.
- GitHub connector PR creation returned HTTP 403 (integration lacks access); scaffold branch itself is pushed and verified. Next: publish this feature branch, merge the scaffold via an authorized GitHub path, integrate Ismail's production pipeline, rerun the CLI and full tests, regenerate the report, verify video and links before submission.
