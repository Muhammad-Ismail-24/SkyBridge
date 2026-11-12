"""Checks the production JSON boundary consumed by Sufiyan's dashboard."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app import ORDER, assignment_rows, load_record, network_dot, solver_metadata, validate_record

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


def test_map_uses_saved_adjacency_and_failure_trace():
    blocked = load_record(RUNS / "shadow_block.json")
    dot = network_dot(blocked, blocked["quantum"]["best_feasible_bits"])
    assert '"HILL" -- "VALLEY_B"' not in dot
    assert '"HILL" -- "VALLEY_C"' in dot
    failure = load_record(RUNS / "relay_failure.json")
    failure_dot = network_dot(failure, failure["quantum"]["best_feasible_bits"])
    assert '"HILL" -- "VALLEY_B" [color="#c0392b", style=dashed' in failure_dot
    healing = failure["healing"]
    assert healing["before"]["quantum"]["connected_teams"] == 1
    assert healing["immediately_after_failure"]["quantum"]["connected_teams"] == 0
    assert healing["replanned"]["quantum"]["connected_teams"] == 1
    before = network_dot(failure, healing["before"]["quantum"]["bits"], disabled_drones=[])
    immediately = network_dot(failure, healing["immediately_after_failure"]["quantum"]["bits"], disabled_drones=["B"])
    replanned = network_dot(failure, healing["replanned"]["quantum"]["bits"], disabled_drones=["B"])
    assert '"HILL" -- "VALLEY_B" [color="#149d72"' in before
    assert '"HILL" -- "VALLEY_B" [color="#c0392b", style=dashed' in immediately
    assert '"HILL" -- "VALLEY_C" [color="#149d72"' in replanned


def test_production_solver_metadata_and_gap():
    record = load_record(RUNS / "base.json")
    metadata = solver_metadata(record)
    assert metadata["backend"] == "qiskit.primitives.StatevectorSampler"
    assert metadata["evaluation_counts"]["total_circuit_evaluations"] > metadata["optimizer_function_evaluations"]
    assert metadata["circuit_depth"] > 0
    assert metadata["circuit_two_qubit_gates"] > 0
    assert metadata["shots"] == 1024


def test_dashboard_renders_failure_story():
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    page = AppTest.from_file(str(ROOT / "app.py")).run(timeout=20)
    page.selectbox[0].set_value(RUNS / "relay_failure.json").run(timeout=20)
    assert not page.exception
    expected = load_record(RUNS / "relay_failure.json")["quantum"]["utility"]
    assert page.metric[0].value == f"{expected:.2f}"
    assert any("B failed before replanning" in item.value for item in page.markdown)
    assert len(page.get("graphviz_chart")) == 3
    assert [m.value for m in page.metric[5:]] == ["29.50", "15.00", "8.25", "14.00", "24.50", "8.00"]
    assert page.metric[3].label == "Relative gap" and page.metric[3].value == "0.0%"
    assert '"HILL" -- "VALLEY_B" [color="#149d72"' in page.get("graphviz_chart")[0].proto.spec
    assert '"HILL" -- "VALLEY_B" [color="#c0392b"' in page.get("graphviz_chart")[1].proto.spec
    assert '"HILL" -- "VALLEY_C" [color="#149d72"' in page.get("graphviz_chart")[2].proto.spec
