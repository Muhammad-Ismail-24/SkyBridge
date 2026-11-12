"""TEST-ONLY reference implementation of the G0 Scenario/evaluator contract.

Why this exists: Zaheen's modules (model/quantum/baseline) consume Ismail's
``src/scenario.py`` and ``src/evaluate.py``, which were not yet in the repository
when the solver work was written. This file transcribes architecture.md §4
literally so the solver can be verified now. It is NOT the production
scenario/evaluator and must not be imported from ``src/``.

``tests/conftest.py`` prefers Ismail's real modules automatically once they
exist; this reference is then only used as an independent cross-check.
"""

from __future__ import annotations

from dataclasses import dataclass, field

ROLE_TABLE = (
    # key, drone, role, utility v_i, energy e_i   (architecture.md §4, synthetic)
    ("A_H", "A", "hill_relay", 1.0, 40.0),
    ("A_N", "A", "north_recon", 8.0, 30.0),
    ("B_V", "B", "valley_relay", 1.0, 35.0),
    ("B_Delivery", "B", "medical_delivery", 6.0, 45.0),
    ("C_V", "C", "valley_relay_alt", 1.0, 30.0),
    ("C_E", "C", "east_recon", 7.0, 35.0),
    ("D_Delivery", "D", "emergency_delivery", 6.0, 40.0),
    ("D_S", "D", "south_recon", 4.0, 25.0),
)
BATTERY = {"A": 85.0, "B": 80.0, "C": 60.0, "D": 55.0}
RESERVE = 15.0
ALPHA = 0.05
POLICY_W = {"mission_first": 3.0, "balanced": 22.0, "coverage_first": 35.0}

NODES = ("Base", "A_H", "B_V", "C_V", "Team")
BASE_EDGES = {("Base", "A_H"), ("A_H", "B_V"), ("A_H", "C_V"), ("B_V", "Team"), ("C_V", "Team")}
HILL = 0
VALLEYS = (2, 4)
SAME_DRONE = ((0, 1), (2, 3), (4, 5), (6, 7))
VALLEY_SLOT = (2, 4)
PAYLOAD = (3, 6)


@dataclass(frozen=True)
class RefRole:
    index: int
    key: str
    drone: str
    role: str
    utility: float
    energy: float


@dataclass(frozen=True)
class RefScenario:
    name: str
    policy: str
    roles: tuple[RefRole, ...]
    battery: dict
    reserve: float
    alpha: float
    relay_reward: float
    disabled_drones: frozenset
    conflict_pairs: tuple[tuple[int, int], ...]
    edges: frozenset
    relay_pairs: tuple[tuple[int, int], ...] = field(default=())


def _edge(edges, a, b) -> bool:
    return (a, b) in edges or (b, a) in edges


def relay_pairs_from_edges(edges) -> tuple[tuple[int, int], ...]:
    """(hill, valley) pairs whose Base-H-V-Team path exists in the link set."""
    if not _edge(edges, "Base", "A_H"):
        return ()
    pairs = []
    for v in VALLEYS:
        key = ROLE_TABLE[v][0]
        if _edge(edges, "A_H", key) and _edge(edges, key, "Team"):
            pairs.append((HILL, v))
    return tuple(pairs)


def reference_scenario(
    name: str = "base",
    policy: str = "balanced",
    *,
    blocked_edges=(),
    disabled_drones=None,
    battery=None,
    utility_override=None,
) -> RefScenario:
    if disabled_drones is None:
        disabled_drones = {"B"} if name == "relay_failure" else set()
    edges = frozenset(e for e in BASE_EDGES if e not in set(blocked_edges))
    roles = []
    for i, (key, drone, role, v, e) in enumerate(ROLE_TABLE):
        if utility_override and i in utility_override:
            v = utility_override[i]
        roles.append(RefRole(i, key, drone, role, v, e))
    return RefScenario(
        name=name,
        policy=policy,
        roles=tuple(roles),
        battery=dict(battery or BATTERY),
        reserve=RESERVE,
        alpha=ALPHA,
        relay_reward=POLICY_W[policy],
        disabled_drones=frozenset(disabled_drones),
        conflict_pairs=SAME_DRONE + (VALLEY_SLOT, PAYLOAD),
        edges=edges,
        relay_pairs=relay_pairs_from_edges(edges),
    )


def ref_is_feasible(bits, sc: RefScenario) -> bool:
    bits = tuple(bits)
    if len(bits) != len(sc.roles) or any(b not in (0, 1) for b in bits):
        return False
    for i, j in sc.conflict_pairs:
        if bits[i] and bits[j]:
            return False
    for r in sc.roles:
        if not bits[r.index]:
            continue
        if r.drone in sc.disabled_drones:
            return False
        if r.energy + sc.reserve > sc.battery[r.drone]:
            return False
    return True


def ref_connected(bits, sc: RefScenario) -> int:
    return int(sum(bits[h] * bits[v] for h, v in sc.relay_pairs) > 0)


def ref_score_feasible(bits, sc: RefScenario) -> dict:
    if not ref_is_feasible(bits, sc):
        raise ValueError(f"infeasible assignment {tuple(bits)}")
    mission = sum(r.utility * bits[r.index] for r in sc.roles)
    energy_pen = sum(sc.alpha * r.energy * bits[r.index] for r in sc.roles)
    connected = ref_connected(bits, sc)
    bonus = sc.relay_reward * connected
    return {
        "mission_score": mission,
        "energy_penalty": energy_pen,
        "connectivity_bonus": bonus,
        "total_utility": mission - energy_pen + bonus,
        "connected_teams": connected,
    }
