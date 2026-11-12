# SkyBridge — Post-Merge Verification & Codebase Audit

- **Audited commit:** `7e84251` on `main` (`fix: complete dashboard failure story and fast Qiskit runs`, Sufiyan Ahmed, 2026-11-12 19:49 PKT), identical to `origin/main` at audit time.
- **Audit time:** 2026-11-12, roughly 20:30–21:10 PKT.
- **Auditor:** Claude Code (Opus 5.5), run from Zaheen's machine. This is the same agent that wrote `src/model.py`, `src/quantum.py` and `src/baseline.py` (commit `325893c`), which is a **conflict of interest**. To offset it, those modules were checked against an oracle written from `architecture.md` alone, not against their own tests.
- **Environment:** macOS (Darwin 25.5.0, Apple Silicon), Python 3.12.13, packages pinned by `requirements.txt` (qiskit 2.6.2, numpy 2.4.6, scipy 1.17.1, streamlit 1.67.0, python-docx 1.2.0, pytest 9.2.0).
- **Clean clone:** `git clone https://github.com/Muhammad-Ismail-24/SkyBridge.git` into a scratch folder, a fresh venv, then `pip install -r requirements.txt`.
- **No production code was changed.** This file is the only file added. It was first written to `docs/POST_MERGE_AUDIT.md` as requested, then moved to `artifacts/` before committing so the strict structure gate keeps passing (see F-L1).

---

## 1. Executive Verdict

**CONDITIONAL PASS — the code is technically ready for submission. Three human deliverables are still open, and they block submission (not code defects):**

1. The ≤3-minute video pitch does not exist in any form I can inspect.
2. `.skybridge-phase` is still `implementation`, so `scripts/verify_submission.py` reports `PENDING`.
3. The organiser form has not been submitted, and the deadline timezone is unconfirmed.

On the technical side:
- **Mathematics:** correct, confirmed by an independent oracle.
- **Exact baseline:** correct and independent of the quantum solver.
- **QAOA:** genuine, and its output comes only from sampled circuits.
- **Integration and reproducibility:** confirmed from a clean clone; all five scenarios reproduce the committed results.

The report and README describe the results honestly. No issue found is CRITICAL. One is HIGH (the missing deliverables above), and the MEDIUM items affect how convincing the submission looks, not whether it is correct.

---

## 2. Merge Integrity

**Verdict: VERIFIED.**

| Check | Evidence | Result |
|---|---|---|
| Branch / HEAD | `git status -sb` → `## main...origin/main`; HEAD `7e84251` | On `main`, in sync with remote |
| Contributions merged | `git log --graph --all`: `325893c` (Zaheen) → `6faee91`, `2c4f446` (Sufiyan) → `f553286…aa2440b` (Ismail) → merge `8ce78c2` → `83288e9`, `7e84251` | All three owners' commits are ancestors of `main` |
| Expected files present | `git ls-files` matches the architecture.md §6 tree, including `run.py`, all 7 `src/` modules, 5 test modules, 4 scripts, the DOCX and the figure | Present |
| Merge conflicts left | `grep -rn '<<<<<<<\|>>>>>>>'` (excluding `.venv`, `.git`) | None |
| Accidental overwrites | `git diff 325893c HEAD -- src/model.py src/baseline.py tests/test_exact.py tests/conftest.py tests/reference_contract.py` is empty. `src/quantum.py` (+29/−12) and `tests/test_model.py` (+24/−4) were changed by Sufiyan in `7e84251` | Intentional, reviewed: transpile replaced by an exact RZZ→CX·RZ·CX expansion (used only for gate-count metadata) and a stricter `ran_qiskit` flag. Solver behaviour unchanged |
| Duplicate implementations | One QUBO builder, one evaluator, one exact solver. The test-only `tests/reference_contract.py` is never imported from `src/` | None in production |
| Interface compatibility | `pipeline._load_solvers` imports `build_qubo`, `build_hamiltonian`, `solve_exact`, `solve_qaoa`. `Scenario` exposes `roles[i].key/drone/utility/energy`, `battery`, `reserve`, `alpha`, `relay_reward`, `conflict_pairs`, `relay_pairs`, `disabled_drones`, which `model.model_inputs_from_scenario` reads | Compatible: 0 mismatches in the 256-state oracle (§5) |
| Config consistency | `requirements.txt` pins the full stack and installed cleanly. CI uses Python 3.11 but runs only the structure check (F-M1) | Consistent, with that one gap |
| Uncommitted changes | `git status` clean before this file was written | Clean |
| Missing contributor work | `CLAUDE.md` from Ismail's branch was deliberately left out of `main` because the strict structure checker rejects it (COMPLETION_REPORT, 19:25 entry). No functional loss | None functional |

When `tests/conftest.py` can import the production `src.scenario` and `src.evaluate`, it uses them. The QUBO tests are therefore exercised against Ismail's real scenario, not only against the reference copy.

---

## 3. Requirements Traceability

Sources inspected directly:
- **[B]** `Qiskit_Hackathon_Optimization.docx` (organiser brief and rubric)
- **[A]** `architecture.md`
- **[W]** `work_division.md`
- **[S]** `SkyBridge_Project_Specification.docx`

The repo copies of [A] and [W] are byte-identical to the uploaded ones. `REPOSITORY_STRUCTURE.md` was also uploaded, but it describes a different project (App-Dev-Debuggers / NaSCon) and does not apply. M = mandatory (organiser), T = team-mandatory (P0 / team contract), O = optional extension.

| ID | Source | Type | Requirement | Implementation | Verification | Status |
|---|---|---|---|---|---|---|
| R1 | B §Deliverables, A §10 | M | One eligible domain | README, DOCX: "UAVs & Robotics" | Read both | VERIFIED |
| R2 | B 01 | M | Concrete problem and users | README ¶1, DOCX "Problem and intended users" | Read | VERIFIED |
| R3 | B 02 | M | Decision variables | `src/scenario.py` `ROLE_KEYS`, DOCX table | Oracle §5 | VERIFIED |
| R4 | B 02 | M | Objective function | `src/evaluate.py:score_feasible`, `src/model.py:build_qubo` | Oracle: 0 mismatches over 256 states × 5 scenarios | VERIFIED |
| R5 | B 02 | M | Constraints | `evaluate.is_feasible`, `Scenario.conflict_pairs/forbidden_indices` | Oracle plus edge cases §6 | VERIFIED |
| R6 | B 02 | M | Small test instance | `data/base.json` (4 drones, 8 bits) | Read; values match A §4 | VERIFIED |
| R7 | B 03 | M | Justify algorithm and show representation | DOCX "Why QAOA…", README | Read | PARTIALLY VERIFIED: justification present, but the DOCX omits penalty value, term counts and circuit depth (F-M3) |
| R8 | B 04 | M | Working Qiskit quantum component | `src/quantum.py` (`qaoa_ansatz`, `StatevectorEstimator`, `StatevectorSampler`) | Fresh clean-clone runs §6 | VERIFIED |
| R9 | B 05 | M | Classical / exact reference | `src/baseline.py:solve_exact` | Oracle optimum = exact optimum for 5/5 scenarios | VERIFIED |
| R10 | B 06 | M | Reflection on limitations and trade-offs | README "Results and limitations", DOCX "Limitations" | Read | VERIFIED |
| R11 | B Deliverables | M | Public GitHub repo with working code | `gh api …/SkyBridge` → `"visibility":"public"`; signed-out `curl` → 200 | Executed | VERIFIED |
| R12 | B Deliverables | M | Reproducible demonstration | README commands | Clean clone: install, 192 tests, 5 CLI runs reproduce committed values | VERIFIED |
| R13 | B Deliverables | M | Report with architecture diagram, results, baseline comparison, limitations | `report/SkyBridge_Hackathon_Report.docx` (1 embedded PNG, 2 tables) | Text extracted; table values match current JSON | VERIFIED (figure quality: F-M2) |
| R14 | B Deliverables | M | ≤3-minute pitch / demo link | — | Nothing in repo, README or COMPLETION_REPORT | NOT IMPLEMENTED / NOT VERIFIABLE (F-H1) |
| R15 | A §10 | M | Submit via form before cutoff, no later commits | — | Outside the repo | NOT VERIFIABLE (F-H1) |
| R16 | A §1 P0.1 | T | Explicit adjacency matrix | `data/base.json` `link_matrix`, validated symmetric 0/1 | Invalid-input tests §6 | VERIFIED |
| R17 | A §1 P0.2 | T | QUBO and Ising from the same scenario used for evaluation | `pipeline._solve`: one `load_scenario` feeds `build_qubo`, `solve_exact`, `decode_samples` | Code read | VERIFIED |
| R18 | A §1 P0.3 | T | QAOA on a local statevector simulator; sampled bitstrings; no hard-coded answer | `quantum.solve_qaoa` | Grep finds no result literals in `src/`, `run.py`, `app.py`; samples vary by seed | VERIFIED |
| R19 | A §1 P0.4 | T | Enumerate all 256 states | `baseline.solve_exact` | `enumerated_states=256` in every run | VERIFIED |
| R20 | A §1 P0.5 | T | Save both results, gap, settings; label quantum vs exact separately | `artifacts/runs/*.json` keys `quantum`, `exact`, `comparison` | Read and regenerated | VERIFIED |
| R21 | A §1 P0.6 | T | Diagram / UI of drones, links, assignments | `app.py` (Streamlit), reads JSON | `tests/test_dashboard.py` (AppTest), 9 tests | VERIFIED (flaky timeout: F-M4) |
| R22 | A §1 P0.7 | T | Clean-clone reproduction with pinned dependencies and fixed seeds | `requirements.txt`, seed 42 | Clean clone on Python 3.12: all headline values reproduce | VERIFIED (not bit-identical across interpreters: F-L3) |
| R23 | A §4.1 | T | One role per drone, unique valley, one payload | `Scenario.conflict_pairs` (6 pairs) | Oracle | VERIFIED |
| R24 | A §4.1 | T | Battery reserve `e+15 ≤ battery` | `evaluate.is_feasible`, `Scenario.forbidden_indices` | Boundary test: D=55 allowed, D=54.9 forbids D_Delivery | VERIFIED |
| R25 | A §4.1 | T | `relay_failure` disables B entirely | `data/relay_failure.json` `disabled_drones:["B"]` | Forbidden = (2,3); exact and QAOA plans have x2=x3=0 | VERIFIED |
| R26 | A §4.2 | T | Connectivity only with hill AND a linked valley | `network.connected_T`, `Scenario.relay_pairs` | Oracle with l_B/l_C; shadow_block relay_pairs = [(0,4)] | VERIFIED |
| R27 | A §4.3 | T | Penalty from an explicit bound, logged | `model.penalty_lower_bound`; JSON `model.penalty_bound`, `penalty_derivation` | Oracle recomputes the bound in all 5 scenarios | VERIFIED |
| R28 | A §4.3 | T | Ising via `SparsePauliOp`, separate offset, 256-state check | `model.build_hamiltonian`, `energy_table` | Max error 0.0 (5 scenarios), ≤2.2e-14 (generic n=4..12) | VERIFIED |
| R29 | A §6 | T | Exact solver uses `is_feasible`/`score_feasible`, not QUBO or QAOA | `baseline.solve_exact` | Test `test_uses_true_utility_not_qubo_energy` plus code read | VERIFIED |
| R30 | A §6 | T | Deterministic tie-break | `baseline.TIE_BREAKER` | Zero-utility case: 63-way tie resolves to all-zeros (lexicographically smallest) | VERIFIED |
| R31 | A §6 | T | Explicit little-endian conversion, tested on only-x0 and only-x7 | `model.qiskit_bitstring_to_bits` | `test_only_x0_and_only_x7_endianness`, Statevector label test | VERIFIED |
| R32 | A §6.1 | T | Canonical tree, strict structure gate, phase file | `scripts/verify_structure.py`, `.skybridge-phase`, CI | Tracked and submission phases PASS. Phase still `implementation` | PARTIALLY VERIFIED (F-H1) |
| R33 | A §9 / W §8 | T | Completion report updated with evidence | `artifacts/COMPLETION_REPORT.md` | Read: all three owners have entries | VERIFIED |
| R34 | A §2 P1 | O | Self-healing: fail B, re-solve, before → loss → replanned | `pipeline.build_healing`, `run.py` | Fresh run: quantum and exact both go A_H,B_V,C_E,D_Delivery → loses link → A_H,C_V,D_Delivery, `recovered=True` | VERIFIED |
| R35 | A §2 P2 | O | Three policy presets re-solved | `data/policy_presets.json`, `--policy-sweep` | mission_first changes the plan (drops relay); coverage_first does not, with a data-derived explanation | VERIFIED |
| R36 | A §2 P3 | O | ShadowMap: one matrix drives scoring and map | `load_scenario("shadow_block")`, `app.py` reads `scenario_meta.link_matrix` | Plan changes to C_V route; dashboard test reads the same matrix | VERIFIED |
| R37 | A §2 P4–P7 | O | Future features | — | — | NOT IMPLEMENTED (deferred by design) |

**Tally (R1–R33, the applicable mandatory and team-mandatory rows):** 29 VERIFIED, 2 PARTIALLY VERIFIED (R7, R32), 1 NOT IMPLEMENTED (R14, video), 1 NOT VERIFIABLE (R15, form/cutoff). All three optional P1–P3 rows are VERIFIED.

---

## 4. Architecture Assessment

```
data/*.json ──load_scenario──▶ Scenario (src/scenario.py, validated)
                                   │
          ┌────────────────────────┼─────────────────────────┐
          ▼                        ▼                         ▼
 build_qubo → build_hamiltonian   solve_exact (src/baseline)  is_feasible / score_feasible
 (src/model)                      uses evaluate only          (src/evaluate + src/network)
          │                        │                         ▲
          ▼                        │                         │
 solve_qaoa (src/quantum)          │      decode_samples ────┘  (src/pipeline)
 qaoa_ansatz + Estimator + COBYLA  │      re-judges every sample
 + StatevectorSampler ─────────────┼──────▶ best feasible sample
                                   ▼
                 pipeline._solve: comparison, constraint_checks, diagnostics, healing
                                   │
                    run.py ──▶ artifacts/runs/*.json ──▶ app.py (dashboard), scripts/generate_report.py (DOCX)
```

- **Data flow:** confirmed by running `pipeline.run_scenario` for all five scenarios.
- **Imports:** no circular imports. `quantum` imports `baseline` only for the `resolve_evaluator` and `total_utility` helpers, never `solve_exact`; the test `test_qaoa_does_not_call_exact_solver` monkeypatches `solve_exact` to raise and the run still completes.
- **Single feasibility judge:** the pipeline re-judges samples with `evaluate.is_feasible`. `quantum.select_feasible` is used only by the solver tests, so production has one feasibility judge.
- **No bypasses:** the dashboard only reads JSON (`app.py:47`). `grep` finds no hard-coded result values (29.5, 24.5, 42.5, 18.25, 27.0) in `src/`, `run.py`, `app.py` or `scripts/`.
- **Dead code:** `quantum.select_feasible` and `quantum.probability_of` are unused by production (the pipeline has equivalents); they remain covered by tests. This is minor duplicated logic (F-L5).

---

## 5. Mathematical Verification

An oracle (scratch script, not committed) rebuilt everything from `architecture.md` §4 using only the published constants (v, e, batteries, reserve 15, α=0.05, W presets, six conflict pairs, l_B/l_C). It imported nothing from `src/` for the maths, then compared against the production `load_scenario → build_qubo → build_hamiltonian → solve_exact` path.

| Scenario | P (impl) | Bound (impl = oracle) | Linear terms match | Quadratic terms match | Ising max error (terms / Qiskit diagonal) | Evaluator mismatches (256) | max\|E+U\| on feasible | QUBO ground state feasible | Oracle optimum = exact |
|---|---|---|---|---|---|---|---|---|---|
| base / balanced | 45.0 | 44 | ✓ | ✓ | 0.0 / 0.0 | 0 | 0.0 | ✓ | `10100110` U=29.5 ✓ |
| base / mission_first | 7.5 | 6.5 | ✓ | ✓ | 0.0 / 0.0 | 0 | 0.0 | ✓ | `01010101` U=18.25 ✓ |
| base / coverage_first | 71.0 | 70 | ✓ | ✓ | 0.0 / 0.0 | 0 | 0.0 | ✓ | `10100110` U=42.5 ✓ |
| relay_failure | 45.0 | 44 | ✓ | ✓ | 0.0 / 0.0 | 0 | 0.0 | ✓ | `10001010` U=24.5 ✓ |
| shadow_block | 23.0 | 22 | ✓ | ✓ | 0.0 / 0.0 | 0 | 0.0 | ✓ | `10011001` U=27.0 ✓ |

(Bitstrings are canonical x0…x7.)

- **Variables:** index i ↔ role `ROLE_KEYS[i]` ↔ qubit i everywhere. The loader *rejects* any reordering of roles (`scenario._validate`).
- **Objective sign:** `E(x) = −U(x)` holds exactly on every feasible state (column "max\|E+U\|" = 0.0), so maximising U is equivalent to minimising E on the feasible set.
- **Constraints:**
  - Six conflict pairs, each with penalty +P·xᵢxⱼ.
  - Forbidden roles (battery or disabled drone) each add +P·xᵢ.
  - Boundaries checked: `e+reserve == battery` is allowed; 0.1 below the battery forbids the role.
  - With all drones disabled, only the empty plan is feasible, and both solvers return it.
- **Ising mapping:**
  - Substitution is xᵢ=(1−Zᵢ)/2. Resulting coefficients: offset = Σaᵢ/2 + Σbᵢⱼ/4, hᵢ = −aᵢ/2 − Σⱼbᵢⱼ/4, Jᵢⱼ = bᵢⱼ/4.
  - Checked two independent ways: reading the Pauli labels, and Qiskit's own `to_matrix().diagonal()`. Both give exact zero error.
  - It also holds on generic random instances with n = 4, 6, 10, 12 (max error ≤ 2.2e-14).
- **Penalty sufficiency (proof, not just the four scenarios):**
  - Take any infeasible x and switch off one variable i that violates a constraint. The energy changes by ΔE ≤ max(cᵢ,0) + Σⱼ Wᵢⱼ − P.
  - So P > B = maxᵢ(max(cᵢ,0) + ΣⱼWᵢⱼ) guarantees every infeasible state has a strictly lower feasible neighbour, which makes the ground state feasible.
  - The oracle recomputed B independently in every scenario. `build_qubo` rejects any explicit P ≤ B.
  - Empirically the bound is sufficient but not tight: on base, a raw QUBO still has a feasible ground state at P=20, and only fails at P=10 (ground state becomes the infeasible `10101010`).
  - architecture.md's *example* bound Σ|cᵢ|+W+1 counts W only once, even though x0 touches two relay pairs. It is therefore not a proven sufficient condition: for coverage_first it gives 60.5, below the rigorous 70 (F-I2). The implementation uses the rigorous bound.

**Mathematical correctness verdict: CORRECT** for the specified model. The pairwise connectivity term is exact only for this one-hill / two-valley topology, as the spec itself states.

---

## 6. Classical vs Quantum Results

**Production runs**, regenerated fresh in the clean clone with `pipeline.run_scenario(..., write=False)` (identical to `run.py --no-write`). Settings: p=1, 1024 shots, seed 42, COBYLA maxiter 80.

| Scenario | Classical optimum | Best QAOA feasible result | Feasible rate (uniform random) | P(optimum) per shot (uniform 0.0039) | Optimality gap | Status |
|---|---|---|---|---|---|---|
| base / balanced | `10100110` A_H,B_V,C_E,D_Delivery, **29.5** | same, **29.5** | 0.851 (0.246) | 0.0127 | 0.0 | MATCH, reproduces committed JSON |
| relay_failure | `10001010` A_H,C_V,D_Delivery, **24.5** | same, **24.5** | 0.631 (0.105) | 0.0225 | 0.0 | MATCH, reproduces committed JSON |
| base / mission_first | `01010101` all recon/delivery, **18.25** | same, **18.25** | 0.729 (0.246) | 0.0479 | 0.0 | MATCH, sample counts bit-identical to committed |
| base / coverage_first | `10100110`, **42.5** | same, **42.5** | 0.853 vs committed 0.852 (0.246) | 0.0176 | 0.0 | MATCH (feasible rate differs in the 3rd decimal: F-L3) |
| shadow_block | `10011001` A_H,B_Delivery,C_V,D_S, **27.0** | same, **27.0** | 0.818 (0.246) | 0.0195 | 0.0 | MATCH, sample counts bit-identical to committed |

**Historical claims, re-checked:**

| Claim | Result |
|---|---|
| "48 passing tests" (solver suite, pre-merge) | Superseded. 49 solver tests now (`test_model` 35, `test_exact` 14), all passing within 192 total |
| "Four scenarios matching classical optimum" | Re-verified for **five** scenarios on the merged code |
| "≈84 % feasible shots" | Pre-merge figure was 2048 shots. Merged runs use 1024 shots: base 0.851; 20 seeds range 0.829–0.860 |

**Robustness** (scratch sweep script; full numbers saved locally in the scratchpad file `robust.json`, not committed):

- **Seeds (p=1, 1024 shots, seeds 0–19):** the optimum was in the samples for 20/20 seeds in all five scenarios. Feasible rate ranges: base 0.829–0.860, relay_failure 0.607–0.650, shadow 0.784–0.821, mission 0.697–0.765, coverage 0.829–0.873.
  - The optimised angles do not depend on the seed (the Estimator is exact), so this measures sampling noise only.
- **Shot budget, base (10 seeds each):** fraction of runs that found the optimum.

  | Shots | QAOA | Uniform random |
  |---|---|---|
  | 16 | 1/10 | 6.1 % |
  | 64 | 7/10 | 22.2 % |
  | 256 | 10/10 | 63.3 % |

  - relay_failure at 64 shots: 7/10 (uniform 22.2 %). shadow_block and mission_first at 64 shots: 10/10.
  - **This low-shot comparison is the fairest evidence that the quantum circuit does useful work.** At 1024 shots, random sampling would also find the optimum 98.2 % of the time.
- **Depth p=1..4 (seed 42, 2048 shots).** "Normalised energy" is (E_uniform − ⟨E⟩)/(E_uniform − E_min).

  | Scenario | Normalised energy p1 → p4 | Feasible rate p1 → p4 | P(opt) p1 → p4 |
  |---|---|---|---|
  | base | 0.68 → 0.75 → 0.79 → 0.81 | 0.84 → 0.98 | 0.016 → 0.048 |
  | mission_first | 0.46 → 0.86 | — | 0.048 → 0.41 |
  | coverage_first | 0.69 → 0.78 | — | ≈0.015 throughout (no concentration gain) |

  - Gate cost grows from 16 CX (depth 19) at p=1 to 64 CX (depth 52) at p=4.
- **Starting angles (base, p=1, COBYLA from 20 random (γ,β) starts, no grid):** median ⟨E⟩ = 1.77, worst 18.77, best −5.18. Only 9/20 reached the grid warm-start optimum (−5.18).
  - The p=1 landscape has several local minima, so the grid warm start in `quantum.py` matters (F-I3).
- **Problem size:** the pipeline accepts only the fixed 8-role instance (the loader enforces it), so larger *scenarios* are **not verifiable** end to end. `model.py` and `quantum.py` are size-generic: random instances at n = 4, 6, 10, 12 build, map exactly, and run QAOA in 0.18–0.54 s.
- **Approximation ratio caveat:** the mean true utility over feasible shots, divided by U*, is 0.34–0.57 at p=1. QAOA at p=1 spreads probability broadly; it does not concentrate on the optimum.

**QAOA correctness verdict: CORRECT AND GENUINE.**
- **Cost layer:** `qaoa_ansatz` applies the production `SparsePauliOp` (scaled by its largest coefficient, a γ rescaling only), with the X mixer.
- **What COBYLA minimises:** the Estimator expectation of the *unscaled* H plus the offset.
- **Parameter binding:** done by name and checked by `test_expectation_matches_statevector_on_diagonal`.
- **Sampling:** the samples come from `StatevectorSampler` and are decoded little-endian.
- **Feasibility:** every sample is re-judged by `evaluate.is_feasible`. No exact result is ever substituted (`pipeline._solve`, lines 187–198; a missing feasible sample yields `no_feasible_sample`).
- **No quantum advantage** is shown or claimed, and both the README and the DOCX say so explicitly.

---

## 7. Test Results

| Run | Command | Result |
|---|---|---|
| Clean clone, 1st run | `.venv/bin/python -m pytest tests -q` | **191 passed, 1 failed** in 136.5 s. Failure: `tests/test_dashboard.py::test_dashboard_renders_failure_story`, `RuntimeError: AppTest script run timed out after 20(s)`. Machine load average was 3.3–4.7 at the time |
| Clean clone, 2nd run | same | 0 failed (grep for FAILED/ERROR was empty) |
| Clean clone, 3rd run | same | **192 passed, 0 failed, 0 skipped** in 4.71 s |
| Per file | `pytest <file> --co -q` | test_constraints 51, test_pipeline 74, test_model 35, test_exact 14, test_network 9, test_dashboard 9 = **192** |
| Structure (tracked) | `scripts/verify_structure.py --phase tracked --strict` | PASS (implementation), exit 0 |
| Structure (submission) | `scripts/verify_structure.py --phase submission --strict` | PASS, exit 0 |
| Submission check | `scripts/verify_submission.py` | **PENDING**: tracked phase is `implementation` |
| CLI | `run.py --scenario base --policy balanced --seed 42 --no-write` | exit 0, `CHECKS all true` |
| CLI (all scenarios) | `pipeline.run_scenario` for all 5 | All `constraint_checks` true; values in §6 |
| Policy sweep | `run.py --policy-sweep --scenario base --seed 42 --from-saved` | exit 0; quantum matches exact for all 3 presets |
| GitHub Actions | `gh run list` | Last 5 runs `success`, but the workflow runs only the structure check (F-M1) |
| Static | `python -m pytest --co` imports every module; no type checker is configured | Imports OK; type checking not configured |

**Untested or weakly tested:**
- CI never runs pytest.
- No test runs `run.py` end to end through a subprocess in CI.
- `scripts/generate_report.py` has no test that the DOCX values equal the JSON (I checked this manually: they match).
- Dashboard rendering is checked headlessly only, not visually.

**Reproducibility limitations:**
- Verified on Python 3.12 with the 3.11 pins, not on 3.11 itself.
- Windows was not tested here (the COMPLETION_REPORT records Sufiyan's Windows runs).
- Bit-level sample counts differ slightly across interpreter and BLAS builds (F-L3).

---

## 8. Findings

### HIGH

**F-H1. Mandatory submission deliverables incomplete.**
- **Files:** `.skybridge-phase:1`; the repo as a whole.
- **Problem:** there is no video pitch or link anywhere. The phase is still `implementation`, so `verify_submission.py` → `SUBMISSION CHECK: PENDING`. COMPLETION_REPORT (19:34 entry) says the video, link check, timezone confirmation and form submission are not done.
- **Evidence:** `git ls-files | grep -iE 'video|mp4'` is empty; README has no video URL.
- **Impact:** the organiser brief lists a ≤3-minute demo link as a deliverable, so submitting without it loses Presentation & defence points (15) and may make the entry incomplete.
- **Fix:** record the video from the existing CLI and dashboard; share it anyone-with-link; test it signed out; set `.skybridge-phase` to `submission`; rerun both verifiers; submit the form before 11:59 PM in the organiser's timezone.

### MEDIUM

**F-M1. CI does not run the test suite.**
- **File:** `.github/workflows/structure.yml:17`.
- **Problem:** the only step is `verify_structure.py --phase tracked --strict`.
- **Impact:** a broken solver or evaluator could merge with a green check. The green badge proves only folder layout.
- **Fix:** add `pip install -r requirements.txt` and `python -m pytest tests -q` (skip or tolerate the Streamlit AppTest if it is slow on runners).

**F-M2. Architecture figure suggests the exact baseline depends on the QUBO.**
- **Files:** `artifacts/figures/architecture.png` (embedded in the DOCX); DOCX caption.
- **Problem:** the horizontal arrow from "QUBO / Ising Model" runs *through* the "Exact Baseline" box into "Shared Evaluation". The figure also omits `pipeline.py` / `run.py` and the JSON artifacts.
- **Caption issue:** it says the figure was "supplied in the canonical starter package", whereas work_division §S3 asks for a figure "exported from the real module graph".
- **Impact:** a judge may read it as the baseline using QUBO energies, which would undercut the independence claim (25 points for meaningful quantum use, 25 for validation).
- **Fix:** redraw with Scenario → {QUBO→Ising→QAOA→samples} and Scenario → Exact baseline as two separate branches meeting at Evaluation → JSON → Dashboard/Report. Then regenerate the DOCX.

**F-M3. DOCX under-documents the quantum mapping.**
- **File:** `report/SkyBridge_Hackathon_Report.docx` (generated by `scripts/generate_report.py`).
- **Problem:** the report never states the penalty value or its derivation (P=45, bound 44), the number of Z and ZZ terms (8 + 8), the offset, the circuit depth or CX count (19 / 16), or the warm-start method.
- **Impact:** rubric B ("correct mapping to a quantum representation", 10 points) rewards exactly this detail, and the data already exists in every run JSON.
- **Fix:** add a short "Quantum representation" paragraph and table, generated from `model.penalty`, `model.penalty_bound` and `quantum.circuit_depth`/`circuit_two_qubit_gates`. Optionally add the low-shot comparison from §6.

**F-M4. Flaky dashboard test.**
- **File:** `tests/test_dashboard.py:83-84`.
- **Problem:** `AppTest.run(timeout=20)` timed out once under load (1 of 3 clean-clone runs).
- **Impact:** a judge who runs `pytest` on a busy laptop may see a red test.
- **Fix:** raise the timeout to 60 s, or mark the test `@pytest.mark.slow` and document it.

### LOW

**F-L1. The requested audit location breaks the strict structure gate. RESOLVED by moving the file.**
- **File:** originally `docs/POST_MERGE_AUDIT.md`; now `artifacts/POST_MERGE_AUDIT.md` (this file).
- **Problem:** `docs/` is not in the architecture.md §6 canonical tree, and `--strict` rejects unapproved top-level folders. It will fail CI.
- **Fix applied:** moved to `artifacts/POST_MERGE_AUDIT.md`, which the canonical tree already permits. Adding a `docs/` folder would need all three owners' agreement (A §6.1).

**F-L2. Windows path separators in the DOCX.**
- **Problem:** the provenance line lists `artifacts\runs\base.json` etc. Cosmetic.
- **Fix:** use `Path.as_posix()` in `scripts/generate_report.py`.

**F-L3. Results are not bit-identical across interpreters.**
- **Evidence:** coverage_first feasible rate is 0.8516 committed (Python 3.11.9, Windows) vs 0.8525 fresh (Python 3.12.13, macOS). Sample-count lists differ for 3/5 scenarios. The chosen plans, utilities, gaps and P(opt) are identical.
- **Fix:** add one sentence to the README: results reproduce to the stated precision; exact counts can vary by platform.

**F-L4. Stale docstring reference.**
- **File:** `src/pipeline.py:53`.
- **Problem:** the docstring cites a "CLAUDE.md rule", but `CLAUDE.md` was intentionally left out of `main`.
- **Fix:** reword it to "file naming convention".

**F-L5. Duplicate sample-judging logic.**
- **Files:** `src/quantum.py` (`select_feasible`, `probability_of`) vs `src/pipeline.py` (`decode_samples`, `quantum_diagnostics`).
- **Problem:** production uses only the pipeline versions. Both use `evaluate.is_feasible`, so there is no correctness risk.
- **Fix:** none needed before submission. Mention it if asked.

### INFORMATIONAL

- **F-I1. A zero gap is not evidence of QAOA quality at 1024 shots.** The README, DOCX and each JSON `comparison.interpretation` already say this. The defensible evidence is the feasible-rate lift (3.4–6× uniform), the P(opt) lift (3–12×) and the low-shot table in §6.
- **F-I2. architecture.md §4.3 example penalty bound** (Σ|cᵢ|+W+1) is not a proven sufficient condition, because x0 has two relay partners. The code uses the rigorous single-flip bound instead. Worth noting in the defence.
- **F-I3. The p=1 COBYLA landscape is multimodal.** Without the 144-point grid warm start, 11/20 random starts end in worse local minima. The README attributes INTERP; the grid scan should also be mentioned when explaining "what the optimiser does".
- **F-I4. The deadline timezone is unconfirmed** (COMPLETION_REPORT 19:34).
- **F-I5. Security:** no credentials, tokens, IBM Runtime usage or broad `except:` in `src/`, `run.py`, `app.py` or `scripts/`. Every dependency is pinned. Output paths are confined to `artifacts/runs` (`pipeline._runs_dir`). Scenario JSON validation is thorough: 7/7 malformed inputs rejected with specific messages, unknown scenario and policy rejected, malformed bit vectors return `False`.

---

## 9. Hackathon Readiness

| Dimension | Assessment |
|---|---|
| **Technical correctness** | Strong. Model, mapping, baseline and QAOA all independently verified; constraints hold in every saved and regenerated plan |
| **Competition compliance** | Incomplete until the video and form are done (F-H1). Everything else in the organiser brief is present and verified |
| **Presentation quality** | Good and honest: README and DOCX avoid speedup claims, label synthetic data, and explain the zero gap. Weakened by the misleading architecture arrow (F-M2) and the thin quantum-mapping section (F-M3) |
| **Judge reproducibility** | A judge can clone, `pip install -r requirements.txt`, run `pytest` (192 pass) and `python run.py …` (sub-second solves), and get the documented numbers. No accounts or credentials needed |

Against the official rubric (evidence only, no score predicted):
- **A. Problem validity:** formulation, constraints and instance all present.
- **B. Quantum use:** mapping verified and QAOA genuine. Documentation of the mapping in the DOCX is the weak point.
- **C. Implementation:** working, interpretable, baseline valid, reproducible.
- **D. Originality:** the two-relay synergy plus failure re-planning is a distinctive model.
- **E. Presentation:** depends on the missing video.

---

## 10. Prioritized Action Plan (before cutoff)

1. **[F-H1, blocking]** Record the ≤3-minute video from `run.py` (base → relay_failure healing → policy sweep `--from-saved`) and the Streamlit dashboard. Upload it, set anyone-with-link, test it signed out, and add the link to the README.
2. **[F-H1, blocking]** Set `.skybridge-phase` to `submission`. Run `verify_structure.py --phase tracked --strict` and `verify_submission.py`, record the outputs in COMPLETION_REPORT, commit and push. Then submit https://forms.gle/jSRrXaHkjVb7G7AK8 before 11:59 PM (confirm the timezone). **No commits after the cutoff.**
3. **[F-M2]** Fix the architecture figure so the exact baseline is visibly independent of the QUBO branch, then regenerate the DOCX.
4. **[F-M3]** Add the quantum-representation details (P and bound, term counts, offset, depth/CX, warm start) and the low-shot comparison to the DOCX via `generate_report.py`.
5. **[F-M1 / F-M4]** Add pytest to CI and raise the dashboard AppTest timeout. Nice to have: if time is short, skip these rather than risk the deadline.

Items 3–5 change files owned by Sufiyan (figure, report, CI, dashboard test) and require their approval. This audit made no changes to them.
