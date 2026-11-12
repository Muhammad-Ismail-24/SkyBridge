"""Checks the public JSON boundary consumed by Sufiyan's dashboard.

The current evidence artifacts are solver runs using a test-only scenario.
The live pipeline test activates once Ismail's CLI is available.
"""
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from app import ORDER, assignment_rows, load_record, validate_record

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "artifacts" / "runs"


@pytest.mark.parametrize("path", sorted(RUNS.glob("*.json")), ids=lambda p: p.stem)
def test_saved_run_is_dashboard_compatible(path):
    record = load_record(path)
    assert record["model"]["role_order"] == list(ORDER)
    assert record["model"]["n_binary"] == 8
    assert record["exact"]["enumerated_states"] == 256
    assert record["quantum"]["ran_qiskit"] is True
    assert record["quantum"] is not record["exact"]
    assert "shots" in record["quantum"] and "enumerated_states" in record["exact"]
    assert record["constraint_checks"]["quantum_best_feasible_rechecked"] is True
    assert record["constraint_checks"]["exact_best_feasible_rechecked"] is True
    assert len(assignment_rows(record)) == 4
    if record["scenario"] == "relay_failure":
        assert record["quantum"]["best_feasible_bits"][2:4] == [0, 0]


def test_bad_records_are_rejected():
    source = load_record(RUNS / "base.json")
    for mutation in (
        lambda d: d.pop("exact"),
        lambda d: d.update(exact=[]),
        lambda d: d["model"].update(role_order=list(reversed(ORDER))),
        lambda d: d["quantum"].update(best_feasible_bits=[1, 0]),
        lambda d: d["quantum"].update(ran_qiskit=False),
        lambda d: d["quantum"]["breakdown"].update(total_utility=-999),
    ):
        record = json.loads(json.dumps(source))
        mutation(record)
        with pytest.raises(ValueError):
            validate_record(record)
    with patch.object(Path, "read_text", return_value="{bad"):
        with pytest.raises(ValueError, match="Cannot load"):
            load_record(ROOT / "bad.json")


@pytest.mark.skipif(not (ROOT / "run.py").exists(), reason="Ismail's production pipeline is pending")
def test_cli_writes_compatible_base_run(tmp_path):
    result = subprocess.run(
        [sys.executable, str(ROOT / "run.py"), "--scenario", "base", "--policy", "balanced", "--seed", "42"],
        cwd=ROOT, capture_output=True, text=True, timeout=180,
    )
    assert result.returncode == 0, result.stderr
    record = load_record(RUNS / "base.json")
    assert record["scenario"] == "base"
    assert record["quantum"]["ran_qiskit"]
