"""Check required deliverables without claiming that structure proves correctness."""
from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check() -> list[str]:
    issues = []
    phase = (ROOT / ".skybridge-phase").read_text(encoding="utf-8").strip()
    if phase != "submission":
        issues.append(f"Tracked phase is {phase!r}; release requires 'submission'.")
    structural = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "verify_structure.py"), "--phase", "submission", "--strict"],
        cwd=ROOT, capture_output=True, text=True,
    )
    if structural.returncode:
        issues.append("Submission structure gate failed:\n" + structural.stdout.strip())
    docx = ROOT / "report" / "SkyBridge_Hackathon_Report.docx"
    if not docx.is_file() or not zipfile.is_zipfile(docx):
        issues.append("The official Word report is missing or invalid.")
    if not (ROOT / "artifacts" / "figures" / "architecture.png").is_file():
        issues.append("Architecture figure is missing.")
    runs = sorted((ROOT / "artifacts" / "runs").glob("*.json"))
    if not runs:
        issues.append("No run JSON artifacts found.")
    for path in runs:
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            issues.append(f"Invalid {path.name}: {exc}")
            continue
        if not record.get("quantum", {}).get("ran_qiskit"):
            issues.append(f"{path.name}: no verified Qiskit run.")
        producer = str(record.get("producer", ""))
        if "reference_contract.py" in producer or "solver-evidence driver" in producer:
            issues.append(f"{path.name}: test-only scenario/evaluator; regenerate through production pipeline.")
    if not (ROOT / "run.py").is_file():
        issues.append("Production CLI run.py is missing.")
    if not (ROOT / "src" / "pipeline.py").is_file():
        issues.append("Production pipeline is missing.")
    return issues


if __name__ == "__main__":
    problems = check()
    if problems:
        print("SUBMISSION CHECK: PENDING")
        for problem in problems:
            print("- " + problem)
        raise SystemExit(1)
    print("SUBMISSION CHECK: PASS (inspect results, demo video, and public links separately)")
