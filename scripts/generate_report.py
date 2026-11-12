"""Generate the evidence-backed SkyBridge Word report from saved run JSON.

This script deliberately labels solver-evidence records until production pipeline
artifacts replace them. It never computes or invents quantum measurements.
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
FIGURE = ROOT / "artifacts" / "figures" / "architecture.png"
ROLES = [
    (0, "A", "Hill relay", 1, 40), (1, "A", "North reconnaissance", 8, 30),
    (2, "B", "Primary valley relay", 1, 35), (3, "B", "Medical delivery", 6, 45),
    (4, "C", "Alternate valley relay", 1, 30), (5, "C", "East reconnaissance", 7, 35),
    (6, "D", "Emergency delivery", 6, 40), (7, "D", "South reconnaissance", 4, 25),
]


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
    doc.add_paragraph("12 November 2026. This report describes an eight-decision synthetic disaster communications problem, the Qiskit solver evidence currently available, and the production integration still required for a reproducible submission.")

    doc.add_heading("Problem and intended users", 1)
    doc.add_paragraph("A disaster may interrupt ground communications. A command operator must assign four battery-limited drones to relay, reconnaissance, and supply roles. A rescue team receives a communications benefit only when a hill relay and one viable valley relay complete the base-to-team path. These illustrative scores are not estimates of saved lives or real radio performance.")
    doc.add_heading("Decision variables and synthetic instance", 1)
    doc.add_paragraph("Each x[i] is binary and indicates whether its drone takes the role below. The order is fixed in the QUBO, Qiskit mapping, exact enumerator, and saved JSON.")
    table(doc, ["Index", "Drone", "Role", "Utility", "Energy"], [[str(v) for v in row] for row in ROLES])
    doc.add_paragraph("Battery budgets: A 85, B 80, C 60, D 55; emergency reserve 15. Base parameters: energy multiplier alpha = 0.05 and connected-team reward W = 22. All are synthetic.")
    doc.add_heading("Objective and constraints", 1)
    doc.add_paragraph("Maximise U(x) = sum_i (v_i - alpha e_i)x_i + W connected_T(x). For valid base links, connected_T(x) = x0(x2 + x4). The QUBO minimises -U(x) plus penalties for conflicts and forbidden roles. The Ising operator uses x_i = (I - Z_i)/2 with a separate constant offset.")
    doc.add_paragraph("Hard limits: at most one role per drone; x2+x4 <= 1 for the valley position; x3+x6 <= 1 for the single payload; role energy plus reserve cannot exceed that drone's battery; and the relay-failure scenario disables both B roles (x2=x3=0). Connectivity is counted only along links in the scenario matrix.")
    doc.add_heading("Why QAOA and how it runs", 1)
    doc.add_paragraph("The small binary, quadratic problem maps naturally to a QUBO and an Ising cost operator. Zaheen's implementation constructs a parameterised QAOA circuit in Qiskit, tunes its angles with SciPy COBYLA, and samples a local StatevectorSampler. Feasible samples are checked against the original constraints and scored using the shared objective. An independent exact solver enumerates all 256 states. QAOA is an approximate method; this demonstration makes no speedup claim.")
    doc.add_heading("System architecture", 1)
    if FIGURE.is_file():
        doc.add_picture(str(FIGURE), width=Inches(6.8))
        doc.add_paragraph("Figure 1. Planned module and evidence flow. Ismail's production scenario, graph, evaluator, and pipeline modules remain pending at the time of this report.")
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
        run = first.get("quantum", {}).get("run", {})
        doc.add_paragraph(f"Example recorded setup: seed {first.get('seed', 'not measured')}; {run.get('n_qubits', 'not measured')} qubits; {run.get('shots', 'not measured')} shots; p={run.get('qaoa_reps', 'not measured')}; {run.get('optimizer', 'optimizer not measured')}; backend {run.get('backend', 'not measured')}. Version details are stored in each JSON record.")
        doc.add_paragraph("Provenance: these files were generated by Zaheen's solver-evidence driver against tests/reference_contract.py, a test-only transcription of the specification. They show genuine Qiskit samples but are not yet output from Ismail's production run_scenario pipeline. Regenerate and recheck them after integration. Source paths: " + ", ".join(str(path.relative_to(ROOT)) for path, _ in records) + ".")
    else:
        doc.add_paragraph("Quantum and exact results pending: no run JSON artifacts were found. No values are inferred from the specification.")
    doc.add_heading("Reproducibility and pending integration", 1)
    doc.add_paragraph("Install the pinned dependencies from requirements.txt using a Python 3.12 virtual environment. Run python -m pytest tests -q and python scripts/verify_structure.py --phase tracked --strict. After Ismail's CLI is merged, run python run.py --scenario base --policy balanced --seed 42 and the relay_failure counterpart. Then regenerate this report using python scripts/generate_report.py. The current environment has not reproduced the full pipeline.")
    doc.add_heading("Limitations and attribution", 1)
    doc.add_paragraph("Four drones and eight bits are a toy instance. Radio links, batteries, and utilities are illustrative; no live sensing, real RF model, flight control, hardware QPU, or life-critical decision support is present. A best sample matching the exact optimum at 2048 shots is not evidence of quantum advantage. QAOA is stochastic; the exact solver is cheap at this size. The production pipeline, verified network map, demo video, and final submission links remain pending.")
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
