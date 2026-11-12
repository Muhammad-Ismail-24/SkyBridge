"""Hard constraints, utility and degraded-plan scoring.

Independent of src/model.py. All numbers are synthetic and illustrative.
"""
from __future__ import annotations

from dataclasses import replace

from src.network import connected_T
from src.scenario import Scenario

N_BITS = 8
VALLEY = (2, 4)
DELIVERY = (3, 6)


def _valid_bits(bits: object) -> bool:
    return (isinstance(bits, (tuple, list)) and len(bits) == N_BITS
            and all(b in (0, 1) and not isinstance(b, bool) for b in bits))


def is_feasible(bits: tuple[int, ...], scenario: Scenario) -> bool:
    """Check all hard constraints from raw scenario fields."""
    if not _valid_bits(bits):
        return False
    per_drone: dict[str, int] = {}
    for role, x in zip(scenario.roles, bits):
        if not x:
            continue
        per_drone[role.drone] = per_drone.get(role.drone, 0) + 1
        if role.drone in scenario.disabled_drones:
            return False
        if role.energy + scenario.reserve > scenario.battery[role.drone]:
            return False
    if any(n > 1 for n in per_drone.values()):
        return False
    if bits[VALLEY[0]] + bits[VALLEY[1]] > 1:
        return False
    if bits[DELIVERY[0]] + bits[DELIVERY[1]] > 1:
        return False
    return True


def check_terms(score: dict) -> None:
    """Assert score terms sum exactly to total_utility."""
    total = score["mission_score"] - score["energy_penalty"] + score["connectivity_bonus"]
    assert score["total_utility"] == total, f"score terms do not sum: {score}"


def score_feasible(bits: tuple[int, ...], scenario: Scenario) -> dict:
    """Utility breakdown; total_utility is None if the plan is infeasible."""
    if not is_feasible(bits, scenario):
        return {"mission_score": None, "energy_penalty": None,
                "connectivity_bonus": None, "total_utility": None,
                "connected_teams": None, "feasible": False}
    mission = sum(r.utility * x for r, x in zip(scenario.roles, bits))
    penalty = scenario.alpha * sum(r.energy * x for r, x in zip(scenario.roles, bits))
    conn = connected_T(bits, scenario)
    bonus = scenario.relay_weight * conn
    score = {"mission_score": mission, "energy_penalty": penalty,
             "connectivity_bonus": bonus,
             "total_utility": mission - penalty + bonus,
             "connected_teams": conn, "feasible": True}
    check_terms(score)
    return score


def score_degraded(bits: tuple[int, ...], failed_drone: str, scenario: Scenario) -> dict:
    """Score a pre-failure plan after removing the failed drone's roles (no re-plan)."""
    if failed_drone not in scenario.battery:
        raise ValueError(f"unknown drone '{failed_drone}'")
    before = score_feasible(bits, scenario)
    lost = [r.index for r, x in zip(scenario.roles, bits)
            if x and r.drone == failed_drone] if _valid_bits(bits) else []
    after_bits = tuple(0 if i in lost else x for i, x in enumerate(bits))
    failed = replace(scenario, disabled_drones=scenario.disabled_drones | {failed_drone})
    after = score_feasible(after_bits, failed)
    after["bits"] = list(after_bits)
    after["lost_roles"] = lost
    after["connectivity_lost"] = bool(before["connected_teams"]) and not after["connected_teams"]
    return after
