# SKYBRIDGE — Work Division, Execution Plan & AI Handoff

**Team:** Zaheen, Ismail, Sufiyan  
**Scope:** Four-drone, eight-binary-variable Qiskit Fall Fest 2026 optimisation project  
**Deadline:** **12 November 2026 at 11:59 PM**; finish code, report, video and link checks **before** cutoff; no pushes after cutoff  
**Primary official domain:** **UAVs & Robotics**, with disaster rescue communications as the use case  
**Technical source of truth:** [`architecture.md`](architecture.md)

> **Priority rule:** The original brief rewards correct Qiskit usage, working code, a mathematical formulation and an exact comparison. Build P0 completely before optional features. **Zaheen receives the most computationally and mathematically complex work.** Owners must share agreed data interfaces early to avoid waiting on each other.

## 1. Ownership at a glance

| Owner | Accountable for | Computational complexity | Target output |
|---|---|---|---|
| **Zaheen — Quantum & optimisation lead** | The mathematics, penalties, complete QUBO→Ising mapping, QAOA circuit + classical optimiser, exact 256-state baseline, quantum result decoding/probabilities, rigorous numerical correctness tests | **Highest — all hardest algorithmic tasks** | `src/model.py`, `src/quantum.py`, `src/baseline.py`, `tests/test_model.py`, `tests/test_exact.py` |
| **Ismail — Simulation & systems lead** | Drone model and synthetic scenarios, radio topology and reachability, all original hard constraint checks, objective breakdown, failure injection, pipeline and result schema | **High — systems logic/integration** | `src/scenario.py`, `src/network.py`, `src/evaluate.py`, `src/pipeline.py`, `run.py`, scenario JSON and tests |
| **Sufiyan — Product, QA & submission lead** | Visual simulation/UI, architecture diagram, end-to-end test/README, repeatability on clean environment, evidence aggregation, formal DOCX report, video pitch, GitHub/form checks | **Moderate–high — delivery and quality** | `app.py` (optional), `README.md`, `scripts/bootstrap_structure.py`, `scripts/verify_structure.py`, `.skybridge-phase`, `.github/workflows/structure.yml`, architecture figure, `.docx` report, video, submitted links |

**Single accountable owner per file.** Everyone reviews outputs; avoid simultaneous conflicting edits. Any helper AI must follow the exact file contract and leave an evidence-based completion report after its assignment.

## 1A. Mandatory repository structure and enforcement — applies to EVERY owner

The canonical folder/file tree is defined in **`architecture.md` §6** and is **mandatory**, not a recommendation. Do not create parallel `backend/`, `frontend/`, `quantum/`, `models/` or `results/` roots, rename modules, relocate `data/`, or write generated solver results outside `artifacts/runs/`. All AI coding agents MUST read the canonical tree before making files. Single-file ownership in §1 applies at those exact paths.

**Sufiyan owns structure enforcement**, but Zaheen and Ismail must run the checker locally before handoff. The repository must contain `scripts/bootstrap_structure.py`, `scripts/verify_structure.py`, `.skybridge-phase`, and `.github/workflows/structure.yml`. Bootstrap is non-destructive: it creates directories and `.gitkeep` placeholders only, never fake solver code or fake results.

```bash
python scripts/bootstrap_structure.py
python scripts/verify_structure.py --phase scaffold --strict       # initially / each branch
python scripts/verify_structure.py --phase implementation --strict # once P0 merges
python scripts/verify_structure.py --phase submission --strict     # before final commit
```

The tracked `.skybridge-phase` file is the CI enforcement stage: `scaffold` → `implementation` → `submission`. Promote it as each gate is completed. The final release commit **must** declare `submission` and pass the corresponding gate. GitHub branch protection should require the `Verify SkyBridge repository structure` workflow when available. A failed check blocks merge or release; never bypass it or silently create alternative directories.

**Agent completion requirement:** include the exact command, PASS/FAIL result, and any structural changes in `artifacts/COMPLETION_REPORT.md`. If the architecture or directory contract legitimately changes, get approval from all three owners and update **both** Markdown specs, the checker, CI and handoff instructions in the same commit.

## 2. Immediate interface agreement (first integration gate)

Before working separately, agree and commit to the following cross-module contract:

```python
# Ismail-owned
load_scenario(name: str, policy: str = "balanced") -> Scenario
is_feasible(bits: tuple[int, ...], scenario: Scenario) -> bool
score_feasible(bits: tuple[int, ...], scenario: Scenario) -> dict

# Zaheen-owned
build_qubo(scenario: Scenario) -> QuboSpec
build_hamiltonian(qubo: QuboSpec) -> HamiltonianSpec
solve_exact(scenario: Scenario) -> ExactResult
solve_qaoa(qubo: QuboSpec, *, seed: int, shots: int, reps: int, maxiter: int) -> QuantumResult

# Ismail-owned orchestration, consumed by Sufiyan
run_scenario(name: str, policy: str = "balanced", seed: int = 42) -> dict
```

Use a fixed variable order `[A_H, A_N, B_V, B_Delivery, C_V, C_E, D_Delivery, D_S]`; 8 logical bits, 256 possible bitstrings. `Scenario` must carry roles, benefits, energy costs, battery budgets, 15-unit reserve, one-package constraint, link matrix, relay reward and policy weights. The JSON produced by `run_scenario` is the **only** source for UI metrics and the report. See `architecture.md` for exact formulas and constraints.

## 3. Zaheen — most complex, highest-risk work (P0 first)

**Mission:** make the quantum computation genuine, correct, defensible and independently validated. Zaheen is the final technical authority on QUBO/Ising correctness and QAOA configuration.

### Z1. Translate the real optimisation model to QUBO — CRITICAL

- Define binary variables, objective `U(x)` and penalty-augmented `E(x)` exactly as `architecture.md`.
- Implement six conflict pairs: four same-drone pairs, one unique valley slot `(2,4)`, one single payload `(3,6)`. Add per-role failure and battery prohibitions.
- Select penalty strength **from an explicit bound**, not an unexplained constant. Log weights and demonstrate constraints have not been silently relaxed.
- Implement `x=(I-Z)/2` mapping to `SparsePauliOp`; store the constant offset and bit ordering.
- **Prove in code** energy agreement for all 256 assignments: QUBO evaluator versus Ising diagonal plus offset.
- Make `build_qubo` depend on scenario data, not a hard-coded bitstring corresponding to a desired outcome.

**Acceptance:** `pytest tests/test_model.py -q` passes and 256-state energy comparison reports maximum numerical error within specified tolerance (e.g. `1e-8`).

### Z2. Build real Qiskit QAOA — CRITICAL

- Implement an 8-qubit QAOA with `qiskit-algorithms` QAOA or an equivalent in-house circuit using Qiskit `QAOAAnsatz` (appropriate for installed SDK).
- Use local `StatevectorSampler` to sample actual circuits. Start with `reps=1`, fixed seed 42, 1024–2048 shots, COBYLA ~80 iterations.
- Show the classical **outer-loop** optimizer is tuning quantum-circuit parameters. Capture evaluation count, best params, sampled distribution, run settings, backend, dependency versions and runtime.
- Decode sample strings with explicit Qiskit little-endian conversion. Do **not** turn an exact baseline optimum into the "quantum result".
- Rank **feasible** sampled candidates using the independent evaluator. If no feasible samples appear, report failure and work on QAOA settings/penalties.
- Keep QAOA outcomes stochastic; do not write tests requiring a particular final assignment from every seed.

**Acceptance:** a real sampled result is saved to `artifacts/runs/base.json` and contains meaningful circuits/sampling metadata, with a clearly labelled feasible quantum assignment (or transparently documented no-feasible-sample outcome).

### Z3. Independent exact baseline and evaluation protocol — CRITICAL

- Enumerate bitstrings 0…255; use Ismail's original constraints and *true* utility (not QUBO penalised energy) to find the exact feasible maximum.
- Deterministic tie-breaking and count feasible/infeasible configurations.
- Compute exact vs quantum **absolute objective gap**, relative gap when defined, feasible sample fraction and selected roles. Maintain separate wall-clock timings; do not claim quantum advantage.
- Validate base and relay-failure scenario, then policy experiments if implemented.
- Expose reusable output to Ismail for pipeline integration and Sufiyan for report tables.

**Acceptance:** `pytest tests/test_exact.py -q` passes, baseline checks 256 bitstrings per scenario, the comparison uses the *same* true utility on both outputs, and output isn't copied from the optimiser.

### Z4. Technical defence evidence

Provide Sufiyan with: formal objective/constraints; why quadratic relay synergy suits QUBO; QAOA choice and limitations; qubit count, circuit depth and shot configuration; saved run outputs; actual performance/optimality numbers; reasons for any quantum shortfall. Credit any borrowed code.

**Do not work on UI, report formatting or video** while the core QAOA/Ising tests remain incomplete.

## 4. Ismail — simulation, constraints and backend integration

**Mission:** create a deterministic, domain-correct world in which Zaheen's optimizer has a meaningful problem and Sufiyan's UI presents truthful state.

### I1. Scenario and data contract — CRITICAL

- Implement `Scenario` and `Role` dataclasses with a stable 8-variable ordering.
- Build 4-drone base instance; reserve/battery units and mission weights must match `architecture.md`.
- Maintain a small fixed adjacency matrix for `Base--Hill--Valley--Team`, including permissible valley alternatives; label it illustrative terrain obstruction, not real RF prediction.
- Supply `base`, `relay_failure` (B disabled), and policy presets. Define failure as B **unable to take any role**, not merely B's relay role.
- All input JSON data schema must be validated with useful errors.

**Acceptance:** `load_scenario` gives stable, fully documented values for every run; all ground links plotted by the UI come from the same adjacency matrix.

### I2. Original constraints, connectivity and objective — CRITICAL

- Implement `is_feasible(bits, scenario)` independently of Zaheen's QUBO builder.
- Enforce one job per drone, one valley slot, one delivery payload, battery reserve, disabled drones, legal graph edges.
- Implement `connected_T(bits, scenario)` based on validated link matrix; no benefit for incomplete relay paths.
- `score_feasible` returns `{mission_score, energy_penalty, connectivity_bonus, total_utility, connected_teams}`. Explicitly reject or mark infeasible inputs.
- Add unit tests for empty state, illegal dual duty, simultaneous deliveries, missing hill relay, both valley options, disconnected link and B failure.

**Acceptance:** constraint tests pass; score terms add up to the reported `total_utility`; no unsupported connectivity is reported.

### I3. Real orchestration and re-planning — P0, then P1

- Implement one CLI (`python run.py --scenario base --policy balanced --seed 42`) that invokes the *actual* model, Qiskit solver and exact baseline, and writes one machine-readable JSON artifact.
- Ensure output has feasible quantum result and exact comparison separately; do not conceal failed/no-feasible QAOA.
- P1: support `--scenario relay_failure`; show the pre-failure selected plan, instantaneous broken link and new reoptimised plan, without adding drones or changing constraints secretly.
- Handle errors, timeouts and missing dependencies with clear messages; keep CLI usable if Streamlit is unavailable.

**Acceptance:** `python run.py --scenario base --policy balanced --seed 42` and failure counterpart generate consistent JSON records, and `pytest tests/test_network.py tests/test_constraints.py -q` passes.

### I4. Extra capability assistance (after P1)

- P2: define `coverage_first (W=35)`, `balanced (W=22)`, `mission_first (W=3)` as synthetic relay-value presets with `α=0.05`, record each weight in the results JSON, and test constraints under every preset. All assignment changes must come from real solver outputs.
- P3: provide a terrain-link override (`shadow_block`) that genuinely changes reachability and model rewards; coordinate display contract with Sufiyan.

## 5. Sufiyan — demo, independent QA, technical writing & submission

**Mission:** make the real outputs understandable, reproducible, accurately documented and submission-ready. **No fabricated quantum results.**

### S1. End-to-end verification and README — CRITICAL

- Write setup commands for a fresh Python 3.11 venv (Windows PowerShell and Unix), dependency installation, exact CLI invocation, tests, optional UI, and result locations.
- Create `tests/test_pipeline.py` to verify an actual CLI run's saved JSON schema, exact/quantum labels, objective breakdown and feasible flags.
- Capture the precise versions that actually worked; coordinate final `requirements.txt` with Zaheen.
- Confirm a clean reproduction on a second terminal/environment if possible.

**Acceptance:** a judge can clone the repository and follow README without manual editing or cloud credentials.

### S2. Small but memorable visual demonstration — CRITICAL AFTER P0

- Build a lightweight Streamlit page **or** static matplotlib storyboard if UI development becomes risky.
- Clearly distinguish **normal**, **failure before replanning**, and **quantum-assisted replanned** state.
- Show base node, hill relay, valley relay, rescue team, active graph edges, drone IDs/roles/battery and lost/retained rescue mission utility.
- Map colors communicate link reachability and must read from Ismail's graph data. Show QAOA's sampled best-feasible plan *and* exact optimum explicitly labelled.
- P2 policy presets invoke real CLI/solver or load cached artifacts from prior genuine runs. Never make controls merely change text without recomputing/reading real results.
- P3 ShadowMap aesthetics only **after** Ismail implements link-aware data; never draw nonexistent radio links.

**Acceptance:** screenshot/demo output matches the JSON artifacts; no hand-authored assignment masquerades as a solver output.

### S3. Formal DOCX report and architecture diagram — MANDATORY

Generate `report/SkyBridge_Hackathon_Report.docx` from **completed code and actual outputs**, using an architecture figure exported from the real module graph. Include:

1. Title, team and official domain; problem, stakeholders and relevance.
2. Binary variables table, objective formula, all hard constraints and synthetic small instance.
3. Why QAOA, QUBO/Ising mapping, sampler/settings, exact baseline methodology.
4. **Architecture diagram embedded in the DOCX** (a `.md` diagram alone is insufficient).
5. Actual experimental setup, scenarios, observed quantum vs exact results in a table, feasibility and gap.
6. Honest limitations: toy 8-bit model, simplistic RF/battery assumptions, QAOA stochasticity, no demonstrated quantum speedup, not deployable for real rescues.
7. Correctly attributed reused code/tutorials if any, references, and reproduction steps.

If an AI writes the report, it **must read `artifacts/runs/*.json`, README and code**, cite those artifacts internally, and use "not measured" for absent values. **Never infer a QAOA result from the exact baseline, invent screenshots, or claim a successful run without a log.**

**Acceptance:** DOCX opens, architecture diagram is legible, every result matches an actual JSON output, all original event checklist items are present.

### S4. Three-minute pitch and release — MANDATORY

- Pitch beats: 0:00–0:25 disaster/problem; 0:25–0:55 two-relay dependency and sacrifice trade-off; 0:55–1:25 QUBO/QAOA; 1:25–2:15 demo (base → B failure → recovery); 2:15–2:40 exact-vs-quantum; 2:40–3:00 limitations/closing.
- Show true outputs and a genuine Qiskit run in the repo/demo. Video ≤3:00; avoid long UI waiting by precomputing results **and clearly labelling those runs as precomputed actual outputs**.
- Check public GitHub link, public share view for video ('anyone with link'), and final commit timestamp **before cutoff**. Never commit after the deadline.
- Submit GitHub, DOCX report and video links through: https://forms.gle/jSRrXaHkjVb7G7AK8

**Acceptance:** an independent person can open all links in incognito and understand the solution and limitations in three minutes.

## 6. Integration handoffs & dependency order

| Gate | Input | Owner to deliver | Receiver / validation | Stop/go criterion |
|---|---|---|---|---|
| **G0** | Shared scenario schema, bit ordering and API signatures | Ismail + Zaheen | All | No mismatched indices, field names or assumptions |
| **G1** | Scenario + constraint/score evaluator | Ismail | Zaheen | Unit tests for six conflict pairs, graph and battery pass |
| **G2** | QUBO, Ising & exact benchmark | Zaheen | Ismail + Sufiyan | 256-state energy equivalence and exact search work |
| **G3** | Actual Qiskit QAOA samples and solver metadata | Zaheen | Ismail | Real circuit run, sample decoding, feasible/failed state explicit |
| **G4** | CLI/orchestrator real results JSON | Ismail | Sufiyan | Base run reproducible end-to-end; then B-failure |
| **G5** | UI + README + DOCX report | Sufiyan | Team | Evidence agrees, report contains architecture, video captures demo |
| **G6** | Final links + Git commit | Sufiyan, with peer checks | All | All links public, final code submitted before cutoff |

**Parallelism:** While Zaheen works on `model.py`/`quantum.py`, Ismail develops scenarios and constraints, and Sufiyan writes README skeleton, diagram and report shell. Final numerical results must be inserted **only after** G3/G4.

## 7. Hard-stop scope and escalation

**If behind schedule:**
1. Preserve: one clean P0 Qiskit run, independent 256-state exact baseline, feasibility proof, README, DOCX report, architecture image, ≤3-min video.
2. Cut: animation polish, real-time UI controls, P3 terrain variant, P2 UI if it adds failure risk.
3. If enough time, implement **P1** before P2, and P2 before P3.
4. Do not implement P4–P7 tonight unless P0–P3 and all submission requirements are already fully validated.
5. Do not claim QAOA outperforms the exact baseline. A negative result is valid if technically honest and properly analysed.

**Escalation owner:** Zaheen resolves mathematical/SDK/quantum-circuit bugs; Ismail resolves scenario/constraint/integration bugs; Sufiyan resolves broken docs, setup, report, UI and submission links. Cross-owner API changes require an explicit agreed update to `architecture.md`.

## 8. Mandatory instructions to AI agents: completion and evidence reporting

Every AI agent used by any teammate **must**:

1. Read `architecture.md`, `work_division.md`, and the original organiser brief before editing.
2. Work only on the assigned module and keep existing signatures unless the team agrees to change them.
3. Run relevant tests and the actual program; record command lines, exit codes and real results.
4. After each meaningful change, append/update `artifacts/COMPLETION_REPORT.md` **without inventing any results**. Include a per-feature status (`DONE / PARTIAL / NOT STARTED / BLOCKED`), changed files, evidence and unresolved issues.
5. Provide an exact next-step handoff to the next owner. Never report a file as completed without checking it exists.
6. Credit any reused third-party code; do not paste tutorials as team-original code.
7. **Do not commit/push after the event cutoff.**

Use this report template (the coding AI must populate it with **observed** information):

```markdown
# SkyBridge — Implementation Completion Report
**As of:** [date/time, timezone]
**Owner/agent:** [person or agent]
**Branch/commit:** [actual ID or "not committed"]

## Requirement and feature status
| ID | Status | Evidence (files/lines or artifacts) | Test/result |
|---|---|---|---|
| P0-A | NOT STARTED | — | — |
| P0-B | NOT STARTED | — | — |
| P0-C | NOT STARTED | — | — |
| P1 | NOT STARTED | — | — |
| P2 | NOT STARTED | — | — |
| P3 | NOT STARTED | — | — |
| P4-P7 | DEFERRED | — | — |

## Files changed
- [actual paths]

## Actual verification commands and outcomes
- `...` — [exit code/pass count/observed output]

## Measured quantum vs exact results
- Source JSON paths: [actual saved files or 'not yet run']
- Quantum feasible result: [actual output / none / not yet run]
- Exact baseline: [actual output / not yet run]
- Gap and feasibility: [actual measurements / not yet run]

## Known defects, limitations and risks
- [observed issues]

## Remaining work and next owner
- [concrete next task, owner, dependency]

## Attribution
- [libraries, tutorials or borrowed code and links]
```

**Also instruct any reporting AI to produce the separate mandatory hackathon report** (`report/SkyBridge_Hackathon_Report.docx`) using the *finished* implementation, not this specification. Its results must be read directly from stored run artifacts, and its architecture image must be embedded in the actual Word document. Internal completion reports do **not** replace the organisers' DOCX deliverable.

## 9. Submission-ready acceptance matrix

| Organiser requirement | Evidence | Owner |
|---|---|---|
| One eligible domain, useful real problem | README / report intro | Sufiyan |
| Variables, objective, constraints, test instance | `architecture.md`, model, DOCX | Zaheen |
| Justified quantum algorithm that does real work | `src/quantum.py`, saved run output | Zaheen |
| Working reproducible Qiskit code | requirements, `run.py`, CI/pytest, README | Zaheen + Ismail + Sufiyan |
| Classical or exact comparison | `src/baseline.py`, JSON/report table | Zaheen |
| Honest technical limitations | DOCX | Sufiyan with Zaheen |
| Architecture diagram **inside report** | Word embedded figure | Sufiyan |
| Public GitHub repo and readable instructions | Published repository link | Sufiyan |
| Video demo ≤3:00 and accessible publicly | Video URL | Sufiyan |
| All links checked / last commit before cutoff | Sign-off log in completion report | All; Sufiyan coordinates |

## 10. Suggested final sign-off

- **Zaheen:** "I verified the mathematical mapping, real QAOA circuit execution and independent exact baseline, and supplied the saved artefacts."
- **Ismail:** "I verified every scenario's constraints, radio graph, failure masks and JSON orchestration."
- **Sufiyan:** "I verified clean reproduction, architecture-in-DOCX, accurate quantum/classical results, ≤3-minute video, publicly accessible links and submission timing."

Only sign off if the statement is **actually true**. The completion report and the official DOCX must represent the project's real state, including any unfinished features.
