"""Evidence-led SkyBridge dashboard. Run with ``streamlit run app.py``."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUNS = ROOT / "artifacts" / "runs"
ORDER = ("A_H", "A_N", "B_V", "B_Delivery", "C_V", "C_E", "D_Delivery", "D_S")
BATTERY = {"A": 85, "B": 80, "C": 60, "D": 55}  # architecture.md synthetic instance


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
    return [
        {"Drone": drone, "Battery (synthetic units)": BATTERY[drone],
         "Assignment": next((ORDER[i] for i in range(8) if bits[i] and ORDER[i].startswith(drone + "_")), "Idle"),
         "Status": "Disabled" if drone == "B" and record["scenario"] == "relay_failure" else "Available"}
        for drone in "ABCD"
    ]


def _source_label(record: dict) -> str:
    producer = str(record.get("producer", ""))
    if "reference_contract.py" in producer or "solver-evidence driver" in producer:
        return "Precomputed Qiskit solver evidence using a test-only scenario/evaluator; production pipeline integration pending."
    return f"Precomputed run artifact: {producer or 'producer unspecified'}"


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
        st.dataframe(rows, hide_index=True, use_container_width=True)
    else:
        st.warning("No feasible QAOA assignment was sampled.")
    st.subheader("Quantum and exact comparison")
    st.dataframe([
        {"Solver": "QAOA sampled best feasible", "Feasible": bool(quantum.get("best_feasible_bits")) and record.get("constraint_checks", {}).get("quantum_best_feasible_rechecked"), "Utility": quantum.get("utility"), "Bits x0…x7": quantum.get("best_feasible_bits"), "Mission": (quantum.get("breakdown") or {}).get("mission_score"), "Energy penalty": (quantum.get("breakdown") or {}).get("energy_penalty"), "Connectivity bonus": (quantum.get("breakdown") or {}).get("connectivity_bonus")},
        {"Solver": "Exact 256-state enumeration", "Feasible": record.get("constraint_checks", {}).get("exact_best_feasible_rechecked"), "Utility": exact.get("utility"), "Bits x0…x7": exact.get("best_bits"), "Mission": (exact.get("breakdown") or {}).get("mission_score"), "Energy penalty": (exact.get("breakdown") or {}).get("energy_penalty"), "Connectivity bonus": (exact.get("breakdown") or {}).get("connectivity_bonus")},
    ], hide_index=True, use_container_width=True)
    st.caption(f"QAOA: {quantum.get('shots', 'unknown')} shots, p={quantum.get('qaoa_reps', 'unknown')}, seed={record.get('seed', 'unknown')}; feasible shot fraction={quantum.get('feasible_sample_fraction')}. Utilities are synthetic.")
    st.subheader("Communication network")
    network = record.get("network")
    if network:
        st.json(network)
    else:
        st.warning("Production adjacency matrix and per-link status are not in this artifact. The connectivity metric above comes from the recorded solver evaluation; no links are drawn without topology data.")
    if record["scenario"] == "relay_failure":
        st.subheader("Self healing")
        base_path = RUNS / "base.json"
        if base_path.is_file():
            try:
                before = load_record(base_path)
            except ValueError:
                before = None
            if before and before.get("policy") == record.get("policy"):
                before_bits = before["quantum"].get("best_feasible_bits")
                after_bits = quantum.get("best_feasible_bits")
                if before_bits and after_bits:
                    stages = st.columns(3)
                    stages[0].markdown(f"**Normal**  \nBase → A hill → {'B' if before_bits[2] else 'C' if before_bits[4] else 'no'} valley → Team  \nConnected: {bool((before['quantum'].get('breakdown') or {}).get('connected_teams'))}  \nUtility: {before['quantum']['utility']:.2f}")
                    stages[1].markdown("**B relay failure**  \nBase → A hill → **broken B link** → Team  \nConnected: False  \nUtility: not scored for the interrupted snapshot")
                    stages[2].markdown(f"**Re-optimised**  \nBase → A hill → {'C' if after_bits[4] else 'no'} valley → Team  \nConnected: {bool((quantum.get('breakdown') or {}).get('connected_teams'))}  \nUtility: {quantum['utility']:.2f}")
                    st.caption("Illustrative two-relay path from the specification. Normal and re-optimised assignments come from separate Qiskit evidence artifacts; the instant broken-link state is an inferred failure effect, not a pipeline measurement.")
        else:
            st.write("Drone B is disabled in this run; its roles are unavailable to the optimiser.")
        st.warning("Production topology and an independently recorded interruption snapshot are pending Ismail's pipeline output.")
    with st.expander("Run provenance and solver metadata"):
        st.json({"producer": record.get("producer"), "generated_at": record.get("generated_at"), "quantum_run": quantum.get("run"), "software_versions": record.get("software_versions")})


if __name__ == "__main__":
    main()
