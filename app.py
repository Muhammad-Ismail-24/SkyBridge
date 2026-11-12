"""Evidence-led SkyBridge dashboard. Run with ``streamlit run app.py``."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUNS = ROOT / "artifacts" / "runs"
ORDER = ("A_H", "A_N", "B_V", "B_Delivery", "C_V", "C_E", "D_Delivery", "D_S")


def validate_record(record: object) -> dict:
    """Reject incomplete or inconsistent run records before displaying metrics."""
    if not isinstance(record, dict):
        raise ValueError("Run JSON must be an object")
    for key in ("scenario", "model", "quantum", "exact", "comparison"):
        if key not in record:
            raise ValueError(f"Missing run field: {key}")
    model, quantum, exact = (record[k] for k in ("model", "quantum", "exact"))
    if not all(isinstance(value, dict) for value in (model, quantum, exact, record["comparison"])):
        raise ValueError("Model, solver results, and comparison must be objects")
    if model.get("n_binary") != 8 or tuple(model.get("role_order", ())) != ORDER:
        raise ValueError("Run does not use the canonical eight-variable order")
    for label, bits in (("quantum", quantum.get("best_feasible_bits")), ("exact", exact.get("best_bits"))):
        if bits is not None and (not isinstance(bits, list) or len(bits) != 8 or any(bit not in (0, 1) for bit in bits)):
            raise ValueError(f"Invalid {label} assignment bits")
    if quantum.get("ran_qiskit") is not True and quantum.get("best_feasible_bits") is not None:
        raise ValueError("A non-Qiskit record cannot claim a quantum assignment")
    if quantum.get("best_feasible_bits") is None and quantum.get("utility") is not None:
        raise ValueError("Quantum utility has no sampled feasible assignment")
    if exact.get("best_bits") is None and exact.get("utility") is not None:
        raise ValueError("Exact utility has no assignment")
    for label, result in (("quantum", quantum), ("exact", exact)):
        breakdown = result.get("breakdown")
        utility = result.get("utility")
        if utility is not None:
            if not isinstance(breakdown, dict) or not all(isinstance(breakdown.get(k), (int, float)) for k in ("mission_score", "energy_penalty", "connectivity_bonus", "total_utility", "connected_teams")):
                raise ValueError(f"Missing {label} objective breakdown")
            expected = breakdown["mission_score"] - breakdown["energy_penalty"] + breakdown["connectivity_bonus"]
            if abs(expected - utility) > 1e-8 or abs(breakdown["total_utility"] - utility) > 1e-8:
                raise ValueError(f"Inconsistent {label} utility")
    return record


def load_record(path: Path) -> dict:
    try:
        return validate_record(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot load {path.name}: {exc}") from exc


def assignment_rows(record: dict, result_key: str = "quantum") -> list[dict]:
    bits = record[result_key].get("best_feasible_bits" if result_key == "quantum" else "best_bits")
    if bits is None:
        return []
    meta = record.get("scenario_meta") or {}
    roles = meta.get("roles") or []
    battery = meta.get("battery") or {}
    disabled = set(meta.get("disabled_drones") or [])
    rows = []
    for drone in "ABCD":
        active = next((r for i, r in enumerate(roles) if i < len(bits) and bits[i] and r.get("drone") == drone), None)
        active_key = next((ORDER[i] for i, bit in enumerate(bits) if bit and ORDER[i].startswith(drone + "_")), None)
        budget = battery.get(drone)
        energy = active.get("energy", 0) if active else 0
        rows.append({"Drone": drone, "Battery budget (synthetic units)": budget,
                     "Remaining after role": budget - energy if isinstance(budget, (int, float)) else None,
                     "Assignment": active.get("name", active_key) if active else (active_key or "Idle"),
                     "Status": "Disabled" if drone in disabled else "Available"})
    return rows


def _source_label(record: dict) -> str:
    producer = str(record.get("producer", ""))
    if "reference_contract.py" in producer or "solver-evidence driver" in producer:
        return "Precomputed Qiskit solver evidence using a test-only scenario/evaluator; production pipeline integration pending."
    if record.get("output_file") and record.get("scenario_meta"):
        return f"Saved production pipeline run from {record['output_file']}; these are precomputed Qiskit results."
    return f"Precomputed run artifact: {producer or 'producer unspecified'}"


def network_dot(record: dict, bits: list[int]) -> str:
    """Draw only links present in Ismail's scenario adjacency matrix."""
    meta = record.get("scenario_meta") or {}
    nodes, matrix = meta.get("link_nodes"), meta.get("link_matrix")
    if not isinstance(nodes, list) or not isinstance(matrix, list) or len(nodes) != len(matrix):
        raise ValueError("Production link matrix is unavailable")
    enabled = {"BASE": True, "TEAM": True, "HILL": bool(bits[0]),
               "VALLEY_B": bool(bits[2]), "VALLEY_C": bool(bits[4])}
    disabled = {"VALLEY_B"} if "B" in (meta.get("disabled_drones") or []) else set()
    reachable = {"BASE"}
    frontier = ["BASE"]
    while frontier:
        source = frontier.pop()
        i = nodes.index(source)
        if not isinstance(matrix[i], list) or len(matrix[i]) != len(nodes):
            raise ValueError("Invalid link matrix row")
        for j, linked in enumerate(matrix[i]):
            neighbor = nodes[j]
            if linked and neighbor not in reachable and enabled.get(neighbor) and neighbor not in disabled:
                reachable.add(neighbor)
                frontier.append(neighbor)
    labels = {"BASE": "Base station", "HILL": "Hill relay · A", "VALLEY_B": "Valley relay · B",
              "VALLEY_C": "Valley relay · C", "TEAM": "Rescue team"}
    lines = ["graph SkyBridge {", 'rankdir=LR; graph [bgcolor="transparent"];',
             'node [shape=box, style="rounded,filled", fontname="Arial"];']
    for node in nodes:
        color = "#fbd5d5" if node in disabled else "#d4f5e5" if node in reachable else "#fff0c2" if enabled.get(node) else "#e5e7eb"
        lines.append(f'"{node}" [label="{labels.get(node, node)}", fillcolor="{color}"];')
    for i, row in enumerate(matrix):
        if not isinstance(row, list) or len(row) != len(nodes):
            raise ValueError("Invalid link matrix row")
        for j in range(i + 1, len(nodes)):
            if row[j]:
                active = enabled.get(nodes[i], False) and enabled.get(nodes[j], False)
                broken = nodes[i] in disabled or nodes[j] in disabled
                color = "#c0392b" if broken else "#149d72" if active and nodes[i] in reachable else "#d88900" if active else "#aab2bf"
                lines.append(f'"{nodes[i]}" -- "{nodes[j]}" [color="{color}", style={"dashed" if broken else "solid"}, penwidth={3 if active or broken else 1.5}];')
    lines.append("}")
    return "\n".join(lines)


def main() -> None:
    import streamlit as st

    st.set_page_config(page_title="SkyBridge Command Centre", page_icon="🚁", layout="wide")
    st.title("SkyBridge Command Centre")
    st.caption("Synthetic disaster response planning · UAVs & Robotics")
    paths = sorted(RUNS.glob("*.json"))
    if not paths:
        st.warning("No solver run artifacts are available. Run the headless CLI when the pipeline is ready.")
        return
    selected = st.selectbox("Recorded scenario", paths, format_func=lambda p: p.stem.replace("_", " ").title())
    try:
        record = load_record(selected)
    except ValueError as exc:
        st.error(str(exc))
        return
    st.info(_source_label(record))
    quantum, exact, comparison = (record[k] for k in ("quantum", "exact", "comparison"))
    if not quantum.get("ran_qiskit"):
        st.warning("This record has no verified Qiskit execution. Quantum metrics are unavailable.")
    cols = st.columns(4)
    cols[0].metric("QAOA sampled best utility", f"{quantum['utility']:.2f}" if quantum.get("utility") is not None else "No feasible sample")
    cols[1].metric("Exact optimum utility", f"{exact['utility']:.2f}" if exact.get("utility") is not None else "Unavailable")
    gap = comparison.get("absolute_gap")
    cols[2].metric("Absolute gap", f"{gap:.2f}" if gap is not None else "Unavailable")
    connected = (quantum.get("breakdown") or {}).get("connected_teams")
    cols[3].metric("Rescue team connected", "Yes" if connected else "No" if connected == 0 else "Unknown")
    st.subheader("Mission assignments")
    rows = assignment_rows(record)
    if rows:
        st.dataframe(rows, hide_index=True, width="stretch")
    else:
        st.warning("No feasible QAOA assignment was sampled.")
    st.subheader("Quantum and exact comparison")
    st.dataframe([
        {"Solver": "QAOA sampled best feasible", "Feasible": bool(quantum.get("best_feasible_bits")) and record.get("constraint_checks", {}).get("quantum_best_feasible_rechecked"), "Utility": quantum.get("utility"), "Bits x0…x7": quantum.get("best_feasible_bits"), "Mission": (quantum.get("breakdown") or {}).get("mission_score"), "Energy penalty": (quantum.get("breakdown") or {}).get("energy_penalty"), "Connectivity bonus": (quantum.get("breakdown") or {}).get("connectivity_bonus")},
        {"Solver": "Exact 256-state enumeration", "Feasible": record.get("constraint_checks", {}).get("exact_best_feasible_rechecked"), "Utility": exact.get("utility"), "Bits x0…x7": exact.get("best_bits"), "Mission": (exact.get("breakdown") or {}).get("mission_score"), "Energy penalty": (exact.get("breakdown") or {}).get("energy_penalty"), "Connectivity bonus": (exact.get("breakdown") or {}).get("connectivity_bonus")},
    ], hide_index=True, width="stretch")
    st.caption(f"QAOA: {quantum.get('shots', 'unknown')} shots, p={quantum.get('qaoa_reps', 'unknown')}, seed={record.get('seed', 'unknown')}; feasible shot fraction={quantum.get('feasible_sample_fraction')}. Utilities are synthetic.")
    if comparison.get("interpretation"):
        st.info(comparison["interpretation"])
    if comparison.get("no_speedup_note"):
        st.caption(comparison["no_speedup_note"])
    st.subheader("Communication network")
    if record.get("scenario_meta", {}).get("link_matrix") and quantum.get("best_feasible_bits"):
        st.graphviz_chart(network_dot(record, quantum["best_feasible_bits"]), width="stretch")
        st.caption("Green is reachable from base; amber is an active but disconnected region; gray is an available inactive link; red dashed links touch a disabled drone. Only edges in the saved adjacency matrix are drawn. " + record["scenario_meta"].get("link_label", ""))
    else:
        st.warning("A valid production adjacency matrix or feasible QAOA assignment is unavailable; no radio links are drawn.")
    if record["scenario"] == "relay_failure":
        st.subheader("Self healing")
        healing = record.get("healing")
        if healing:
            stages = st.columns(3)
            for col, key, title in zip(stages, ("before", "immediately_after_failure", "replanned"), ("Normal", "B failed before replanning", "Re-optimised")):
                state = healing[key]["quantum"]
                col.markdown(f"**{title}**")
                col.write(", ".join(state.get("roles", [])))
                col.metric("Utility", f"{state['breakdown']['total_utility']:.2f}")
                col.write(f"Team connected: {bool(state.get('connected_teams'))}")
            st.caption(healing.get("before_source", "") + ". The immediate failure state is evaluated without a new solve; replanned state comes from the QAOA run.")
        else:
            st.warning("A three-stage healing trace is not in this run artifact.")
    with st.expander("Run provenance and solver metadata"):
        st.json({"producer": record.get("producer"), "generated_at": record.get("generated_at"), "quantum_run": quantum.get("run"), "software_versions": record.get("software_versions")})


if __name__ == "__main__":
    main()
