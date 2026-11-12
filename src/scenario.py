"""Scenario dataclasses and loader.

All values (utilities, energies, batteries, weights, links) are SYNTHETIC and
ILLUSTRATIVE. The link matrix is an illustrative terrain obstruction, not a
real RF prediction. Bit order is [x0..x7] = A_H, A_N, B_V, B_Delivery,
C_V, C_E, D_Delivery, D_S.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SCENARIOS = ("base", "relay_failure", "shadow_block")
POLICIES = ("mission_first", "balanced", "coverage_first")
N_ROLES = 8
BASE_NODES = ("BASE", "HILL", "VALLEY_B", "VALLEY_C", "TEAM")


@dataclass
class Role:
    """One binary decision: a drone taking one role."""
    index: int
    drone: str
    kind: str
    name: str
    utility: float
    energy: float


@dataclass
class Scenario:
    """A fully specified (synthetic) optimisation instance."""
    name: str
    policy: str
    roles: list[Role]
    battery: dict[str, float]
    reserve: float
    alpha: float
    relay_weight: float
    disabled_drones: set[str]
    link_nodes: list[str]
    link_matrix: list[list[int]]
    link_label: str = ""

    def _edge(self, a: str, b: str) -> int:
        i, j = self.link_nodes.index(a), self.link_nodes.index(b)
        return self.link_matrix[i][j]

    @property
    def conflict_pairs(self) -> list[tuple[int, int]]:
        """Same-drone pairs, one valley slot (2,4), one payload (3,6)."""
        pairs: list[tuple[int, int]] = []
        for i, a in enumerate(self.roles):
            for b in self.roles[i + 1:]:
                if a.drone == b.drone:
                    pairs.append((a.index, b.index))
        return pairs + [(2, 4), (3, 6)]

    @property
    def forbidden_indices(self) -> list[int]:
        """Roles of disabled drones, or with energy + reserve > battery."""
        return [r.index for r in self.roles
                if r.drone in self.disabled_drones
                or r.energy + self.reserve > self.battery[r.drone]]

    @property
    def valley_link_flags(self) -> tuple[int, int]:
        """(l_B, l_C): full BASE-HILL-VALLEY-TEAM path availability."""
        def flag(v: str) -> int:
            return (self._edge("BASE", "HILL") * self._edge("HILL", v)
                    * self._edge(v, "TEAM"))
        return flag("VALLEY_B"), flag("VALLEY_C")

    def to_dict(self) -> dict:
        """JSON-serialisable view for run output."""
        return {
            "name": self.name, "policy": self.policy,
            "roles": [vars(r).copy() for r in self.roles],
            "battery": dict(self.battery), "reserve": self.reserve,
            "alpha": self.alpha, "relay_weight": self.relay_weight,
            "disabled_drones": sorted(self.disabled_drones),
            "link_nodes": list(self.link_nodes),
            "link_matrix": [list(r) for r in self.link_matrix],
            "link_label": self.link_label,
            "conflict_pairs": [list(p) for p in self.conflict_pairs],
            "forbidden_indices": self.forbidden_indices,
            "valley_link_flags": list(self.valley_link_flags),
        }


def _num(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a number, got {value!r}")
    if value < 0:
        raise ValueError(f"{label} must be non-negative, got {value}")
    return value


def _validate(raw: dict, source: str) -> None:
    """Raise ValueError with a specific message if raw data is malformed."""
    for key in ("roles", "battery", "reserve", "alpha", "disabled_drones",
                "link_nodes", "link_matrix"):
        if key not in raw:
            raise ValueError(f"{source}: missing field '{key}'")
    roles = raw["roles"]
    if len(roles) != N_ROLES:
        raise ValueError(f"{source}: 'roles' must have length {N_ROLES}, got {len(roles)}")
    drones = set()
    for i, r in enumerate(roles):
        for key in ("drone", "kind", "name", "utility", "energy"):
            if key not in r:
                raise ValueError(f"{source}: roles[{i}] missing field '{key}'")
        _num(r["utility"], f"{source}: roles[{i}].utility")
        _num(r["energy"], f"{source}: roles[{i}].energy")
        drones.add(r["drone"])
    for d in drones:
        if d not in raw["battery"]:
            raise ValueError(f"{source}: battery missing drone '{d}'")
    for d, b in raw["battery"].items():
        _num(b, f"{source}: battery[{d}]")
    _num(raw["reserve"], f"{source}: reserve")
    _num(raw["alpha"], f"{source}: alpha")
    for d in raw["disabled_drones"]:
        if d not in drones:
            raise ValueError(f"{source}: disabled drone '{d}' is not a known drone")
    nodes, m = raw["link_nodes"], raw["link_matrix"]
    for need in BASE_NODES:
        if need not in nodes:
            raise ValueError(f"{source}: link_nodes missing node '{need}'")
    n = len(nodes)
    if len(m) != n or any(len(row) != n for row in m):
        raise ValueError(f"{source}: link_matrix must be {n}x{n} to match link_nodes")
    for i in range(n):
        for j in range(n):
            if m[i][j] not in (0, 1) or isinstance(m[i][j], bool):
                raise ValueError(f"{source}: link_matrix[{i}][{j}] must be 0 or 1")
            if m[i][j] != m[j][i]:
                raise ValueError(f"{source}: link_matrix is not symmetric at ({i},{j})")


def _load_json(filename: str) -> dict:
    path = DATA_DIR / filename
    if not path.exists():
        raise ValueError(f"data file not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{filename}: invalid JSON ({exc})") from exc


def build_scenario(raw: dict, name: str, policy: str, weight: float,
                   source: str = "scenario") -> Scenario:
    """Validate raw dict and build a Scenario."""
    _validate(raw, source)
    roles = [Role(i, r["drone"], r["kind"], r["name"], r["utility"], r["energy"])
             for i, r in enumerate(raw["roles"])]
    return Scenario(
        name=name, policy=policy, roles=roles, battery=dict(raw["battery"]),
        reserve=raw["reserve"], alpha=raw["alpha"], relay_weight=weight,
        disabled_drones=set(raw["disabled_drones"]),
        link_nodes=list(raw["link_nodes"]),
        link_matrix=[list(r) for r in raw["link_matrix"]],
        link_label=raw.get("link_label", ""))


def load_scenario(name: str, policy: str = "balanced") -> Scenario:
    """Load a synthetic scenario. shadow_block = base with HILL-VALLEY_B cut."""
    if name not in SCENARIOS:
        raise ValueError(f"unknown scenario '{name}'; expected one of {SCENARIOS}")
    presets = _load_json("policy_presets.json")
    if policy not in POLICIES or policy not in presets:
        raise ValueError(f"unknown policy '{policy}'; expected one of {POLICIES}")
    weight = _num(presets[policy], f"policy_presets[{policy}]")
    raw = _load_json("relay_failure.json" if name == "relay_failure" else "base.json")
    if name == "shadow_block":
        nodes = raw["link_nodes"]
        i, j = nodes.index("HILL"), nodes.index("VALLEY_B")
        raw["link_matrix"][i][j] = raw["link_matrix"][j][i] = 0
    return build_scenario(raw, name, policy, weight, source=f"{name}.json")
