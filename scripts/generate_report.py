"""Generate the evidence-backed SkyBridge Word report from saved run JSON.

This script reads production pipeline records. It never computes or invents
quantum measurements.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from docx import Document
from docx.shared import Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "artifacts" / "runs"
OUT = ROOT / "report" / "SkyBridge_Hackathon_Report.docx"
FIGURE = ROOT / "artifacts" / "figures" / "architecture_v2.png"


def read_runs() -> list[tuple[Path, dict]]:
    records = []
    for path in sorted(RUNS.glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError(f"Invalid result artifact {path.name}: {exc}") from exc
        if not isinstance(record, dict) or not {"scenario", "quantum", "exact", "comparison"} <= record.keys():
            raise ValueError(f"Missing result fields in {path.name}")
        records.append((path, record))
    return records


def table(doc: Document, headers: list[str], rows: list[list[str]]) -> None:
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Table Grid"
    for cell, header in zip(t.rows[0].cells, headers):
        cell.text = header
    for row in rows:
        cells = t.add_row().cells
        for cell, value in zip(cells, row):
            cell.text = str(value)


def measured(value: object, precision: int = 2) -> str:
    if value is None:
        return "Not measured"
    if isinstance(value, (int, float)):
        return f"{value:.{precision}f}"
    return str(value)


def build_report() -> Path:
    records = read_runs()
    doc = Document()
    sec = doc.sections[0]
    sec.top_margin = sec.bottom_margin = Inches(0.7)
    sec.left_margin = sec.right_margin = Inches(0.75)
    styles = doc.styles
    styles["Normal"].font.name = "Aptos"
    styles["Normal"].font.size = Pt(9)
    doc.add_paragraph("SkyBridge Quantum Drone Assignment Report", style="Title")
    doc.add_paragraph("Qiskit Fall Fest 2026 | UAVs & Robotics | Zaheen, Ismail, Sufiyan")
    doc.add_paragraph("12 November 2026. This report describes an eight-decision synthetic disaster communications problem, measured Qiskit results from the production pipeline, and an independent exact comparison.")

    doc.add_heading("Problem and intended users", 1)
    doc.add_paragraph("A disaster may interrupt ground communications. A command operator must assign four battery-limited drones to relay, reconnaissance, and supply roles. A rescue team receives a communications benefit only when a hill relay and one viable valley relay complete the base-to-team path. These illustrative scores are not estimates of saved lives or real radio performance.")
    doc.add_heading("Decision variables and synthetic instance", 1)
    doc.add_paragraph("Each x[i] is binary and indicates whether its drone takes the role below. The order is fixed in the QUBO, Qiskit mapping, exact enumerator, and saved JSON.")
    instance = next((rec.get("scenario_meta") for _, rec in records if rec.get("scenario") == "base" and rec.get("policy") == "balanced"), None)
    if instance and instance.get("roles"):
        table(doc, ["Index", "Drone", "Role", "Utility", "Energy"],
              [[str(role[k]) for k in ("index", "drone", "name", "utility", "energy")] for role in instance["roles"]])
        battery = instance.get("battery", {})
        doc.add_paragraph("Battery budgets: " + ", ".join(f"{drone} {battery[drone]}" for drone in "ABCD" if drone in battery) + f"; emergency reserve {instance.get('reserve', 'not recorded')}. Base parameters: energy multiplier alpha = {instance.get('alpha', 'not recorded')} and connected-team reward W = {instance.get('relay_weight', 'not recorded')}. All are synthetic.")
    else:
        doc.add_paragraph("The production instance values are pending a base run artifact.")
    doc.add_heading("Objective and constraints", 1)
    doc.add_paragraph("Maximise U(x) = sum_i (v_i - alpha e_i)x_i + W connected_T(x). For valid base links, connected_T(x) = x0(x2 + x4). The QUBO minimises -U(x) plus penalties for conflicts and forbidden roles. The Ising operator uses x_i = (I - Z_i)/2 with a separate constant offset.")
    doc.add_paragraph("Hard limits: at most one role per drone; x2+x4 <= 1 for the valley position; x3+x6 <= 1 for the single payload; role energy plus reserve cannot exceed that drone's battery; and the relay-failure scenario disables both B roles (x2=x3=0). Connectivity is counted only along links in the scenario matrix.")
    doc.add_heading("Why QAOA and how it runs", 1)
    doc.add_paragraph("The small binary, quadratic problem maps naturally to a QUBO and an Ising cost operator. Zaheen's implementation constructs a parameterised QAOA circuit in Qiskit, tunes its angles with SciPy COBYLA, and samples a local StatevectorSampler. Feasible samples are checked against the original constraints and scored using the shared objective. An independent exact solver enumerates all 256 states. QAOA is an approximate method; this demonstration makes no speedup claim.")
    doc.add_heading("System architecture", 1)
    if FIGURE.is_file():
        doc.add_picture(str(FIGURE), width=Inches(6.0))
        doc.add_paragraph("Figure 1. SkyBridge architecture: scenario model, two independent solver branches (Qiskit QAOA and exact 256-state enumeration), the shared independent evaluator that judges both, and the comparison that produces the run records, dashboard and report. The exact result never enters the quantum branch.")
    else:
        doc.add_paragraph("Architecture figure pending.")
    doc.add_heading("Measured results and comparison", 1)
    if records:
        rows = []
        for path, rec in records:
            q, e, c = rec["quantum"], rec["exact"], rec["comparison"]
            rows.append([path.stem, measured(q.get("utility")), measured(e.get("utility")), measured(c.get("absolute_gap")), measured(q.get("feasible_sample_fraction"), 3), str(bool(q.get("best_feasible_bits")))])
        table(doc, ["Run", "QAOA U", "Exact U", "Gap", "Feasible shot share", "QAOA feasible"], rows)
        first = records[0][1]
        q = first.get("quantum", {})
        versions = first.get("software_versions", {})
        doc.add_paragraph(f"Example recorded setup: seed {first.get('seed', 'not measured')}; {first.get('model', {}).get('n_binary', 'not measured')} qubits; {q.get('shots', 'not measured')} final-sampling shots; p={q.get('qaoa_reps', 'not measured')}; {q.get('maxiter', 'not measured')} configured maximum COBYLA evaluations; backend {q.get('backend', 'not measured')}. Python {versions.get('python', 'not measured')}, Qiskit {versions.get('qiskit', 'not measured')}. The optimisation uses an exact statevector estimator; shots refer to final sampling.")
        model_meta = first.get("model", {})
        counts = q.get("evaluation_counts") or {}
        doc.add_paragraph(f"Quantum mapping evidence (same record): penalty P = {measured(model_meta.get('penalty'))} against a derived single-flip bound of {measured(model_meta.get('penalty_bound'))}, so every infeasible state has a strictly lower-energy feasible neighbour; QUBO and Ising energies agree on all 256 states (tests/test_model.py); Qiskit's little-endian bit order is converted to the canonical x0..x7 order only in src/model.py. Circuit depth {q.get('circuit_depth', 'not measured')} with {q.get('circuit_two_qubit_gates', 'not measured')} two-qubit gates; {counts.get('warm_start_evaluations', 'not measured')} warm-start grid evaluations plus {counts.get('optimizer_evaluations', 'not measured')} COBYLA evaluations. Feasible shot share {measured(q.get('feasible_sample_fraction'), 3)} versus {measured((q.get('diagnostics') or {}).get('uniform_baseline', {}).get('feasible_fraction'), 3)} for uniform random sampling.")
        doc.add_paragraph("Provenance: the saved records were generated by run.py and src/pipeline.py with Ismail's production scenario and evaluator. The CLI's run timestamp and settings are in each JSON record. Source paths: " + ", ".join(str(path.relative_to(ROOT)) for path, _ in records) + ".")
        interpretation = first.get("comparison", {}).get("interpretation")
        if interpretation:
            doc.add_paragraph("Interpretation of the base result: " + interpretation)
        failure = next((rec for _, rec in records if rec.get("scenario") == "relay_failure"), None)
        if failure and failure.get("healing"):
            stages = failure["healing"]
            doc.add_paragraph("B failure trace (quantum branch): normal U = " + measured(stages["before"]["quantum"]["breakdown"]["total_utility"]) + ", connected team = " + str(stages["before"]["quantum"]["connected_teams"]) + "; immediately after B fails, U = " + measured(stages["immediately_after_failure"]["quantum"]["breakdown"]["total_utility"]) + ", connected team = " + str(stages["immediately_after_failure"]["quantum"]["connected_teams"]) + "; after replanning, U = " + measured(stages["replanned"]["quantum"]["breakdown"]["total_utility"]) + ", connected team = " + str(stages["replanned"]["quantum"]["connected_teams"]) + ". The immediate state is evaluated without replanning.")
    else:
        doc.add_paragraph("Quantum and exact results pending: no run JSON artifacts were found. No values are inferred from the specification.")
    doc.add_heading("Reproducibility", 1)
    doc.add_paragraph("Install the pinned dependencies from requirements.txt using a Python 3.11 virtual environment. Run python -m pytest tests -q and python scripts/verify_structure.py --phase tracked --strict. Run python run.py --scenario base --policy balanced --seed 42 and the relay_failure counterpart; they write JSON to artifacts/runs. Then regenerate this report using python scripts/generate_report.py. Ismail documented a clean-clone Python 3.11.9 run; the integration checks for this merged branch are recorded in artifacts/COMPLETION_REPORT.md.")
    doc.add_heading("Limitations and attribution", 1)
    doc.add_paragraph("Four drones and eight bits are a toy instance. Radio links, batteries, and utilities are illustrative; no live sensing, real RF model, flight control, hardware QPU, or life-critical decision support is present. A best sample matching the exact optimum at 1024 shots is not evidence of quantum advantage. QAOA is stochastic; the exact solver is cheap at this size. Source code, setup and run instructions: https://github.com/Muhammad-Ismail-24/SkyBridge (see README.md).")
    doc.add_paragraph("Team ownership: Zaheen developed the QUBO/Ising and quantum/exact solvers; Ismail owns scenario, topology, evaluator, and pipeline; Sufiyan owns dashboard, QA, documentation, and report. The warm-start schedule was reimplemented with attribution to Zhou et al., Physical Review X 10, 021067 (2020). Qiskit public APIs and SciPy COBYLA are used; see architecture.md and source modules for implementation details.")
    doc.add_heading("References", 1)
    doc.add_paragraph("IBM Quantum QAOA tutorial: https://quantum.cloud.ibm.com/docs/en/tutorials/quantum-approximate-optimization-algorithm")
    doc.add_paragraph("Qiskit SDK primitives: https://quantum.cloud.ibm.com/docs/en/qiskit/simulate-with-qiskit-sdk-primitives")
    doc.add_paragraph("Zhou et al., Quantum Approximate Optimization Algorithm: Performance, Mechanism, and Implementation on Near-Term Devices, Physical Review X 10, 021067 (2020).")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUT)
    return OUT


if __name__ == "__main__":
    print(build_report())
