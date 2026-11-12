# SkyBridge

SkyBridge is a small research prototype for assigning four radio-equipped drones after a disaster disrupts ground communication. It belongs to the **UAVs & Robotics** domain. A command operator needs to choose hill and valley relay positions while also preserving reconnaissance and supply missions. The instance is synthetic: it is not a flight controller, radio planner, or rescue decision system.

The eight binary decisions have a fixed order: `A_H, A_N, B_V, B_Delivery, C_V, C_E, D_Delivery, D_S`. Each drone can take at most one role. The model also limits the valley slot and delivery payload, respects battery reserves and failure masks, and awards rescue-team connectivity only when a valid hill-to-valley path exists. See [architecture.md](architecture.md) for the exact objective, constraints, topology, and software contracts. [work_division.md](work_division.md) assigns the modules to Zaheen, Ismail, and Sufiyan.

QAOA is used because the assignment is a small binary optimisation problem with quadratic relay synergy and conflicts. `src/model.py` turns its QUBO into an Ising cost Hamiltonian; `src/quantum.py` optimises a Qiskit QAOA circuit and samples it with `StatevectorSampler`. `src/baseline.py` independently checks all 256 bitstrings for the best feasible utility. This is a correctness and demonstration comparison, not a quantum speedup claim.

## Current integration state

Zaheen's solver, exact baseline, and four precomputed Qiskit evidence JSON files are present. Their producer field states that the runs used a test-only scenario/evaluator transcribed from the specification. Ismail's production scenario, graph, evaluator, pipeline, and CLI are pending. The Streamlit dashboard labels this distinction and does not draw unverified active radio links. The evidence records should be regenerated through `run.py` once the production pipeline is merged. `artifacts/COMPLETION_REPORT.md` records verified work and remaining dependencies.

## Installation

Use Python **3.12** for the currently measured dependency set. The architecture originally proposed Python 3.11, which has not yet been independently reproduced. No IBM account is needed for the local statevector simulator.

Windows PowerShell:

```powershell
git clone https://github.com/Muhammad-Ismail-24/SkyBridge.git
cd SkyBridge
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

macOS or Linux:

```bash
git clone https://github.com/Muhammad-Ismail-24/SkyBridge.git
cd SkyBridge
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

If Python 3.12 is unavailable, install it first. The solver's pinned versions were measured on Python 3.12.13; other interpreter versions need verification.

## Run and compare

Once Ismail's `run.py` is merged, from the repository root:

```bash
python run.py --scenario base --policy balanced --seed 42
python run.py --scenario relay_failure --policy balanced --seed 42
python run.py --scenario base --policy mission_first --seed 42
python run.py --scenario base --policy coverage_first --seed 42
```

On Windows, use `.\.venv\Scripts\python.exe` in place of `python`; on Unix use `.venv/bin/python`. The CLI should save genuine run records in `artifacts/runs/`. Until it is merged, the committed JSON files are solver evidence generated against a test-only contract, not full pipeline output. The `quantum` and `exact` sections are separate; a missing feasible quantum sample must remain explicit.

Run the dashboard after dependencies are installed:

```bash
streamlit run app.py
```

Use `.\.venv\Scripts\streamlit.exe run app.py` on Windows or `.venv/bin/streamlit run app.py` on Unix if the executable is not on `PATH`. Select a recorded scenario. The dashboard reads the JSON and shows QAOA and exact scores, assignments, battery budgets, connectivity, solver settings, and provenance. Network links are displayed only when a production record supplies link data.

Run tests and the structure gate:

```bash
python -m pytest tests -q
python scripts/verify_structure.py --phase tracked --strict
```

The integration test for `run.py` skips until that file exists. Quantum model tests need the pinned Qiskit stack. The structure phase remains `scaffold` until all required production modules are merged. The `implementation` and `submission` gates must pass before release.

Generate the Word report from available artifacts:

```bash
python scripts/generate_report.py
python scripts/verify_submission.py
```

The report generator records actual JSON values and labels missing production integration as pending. `verify_submission.py` reports whether all mandatory deliverables are ready; it does not submit the organiser's form. The report is `report/SkyBridge_Hackathon_Report.docx`.

## Results and limitations

The committed Qiskit evidence records report base, relay failure, and two policy presets using seed 42, p=1, and 2048 shots. Read the JSON files for exact numeric values and their producer notes; do not treat cached values as a fresh CLI reproduction. Utility, energy, battery, and radio reachability are illustrative. The eight-variable test is too small to show computational advantage. QAOA sampling is stochastic, and the topology model covers one team with a two-relay path. No physical drone, live map, real RF propagation, hardware QPU, or safety-critical decision capability is claimed.

## Team and attribution

- **Zaheen:** QUBO/Ising mapping, Qiskit QAOA, exact 256-state baseline, solver tests.
- **Ismail:** scenarios, network topology, constraints, objective evaluator, CLI/pipeline.
- **Sufiyan:** dashboard, integration QA, structure, documentation, report, submission preparation.

The team implementation uses Qiskit's public `SparsePauliOp`, `qaoa_ansatz`, and statevector primitives and SciPy COBYLA. The warm-start schedule is attributed in the completion report to Zhou et al., *Physical Review X* 10, 021067 (2020); code was reimplemented. No tutorial code is claimed as original. See the references in `architecture.md` and the generated report for API documentation.
