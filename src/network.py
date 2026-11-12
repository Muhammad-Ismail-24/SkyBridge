"""Radio-link reachability over the scenario's illustrative link matrix.

The matrix is an illustrative terrain obstruction, not a real RF prediction.
"""
from __future__ import annotations

from src.scenario import Scenario


def linked(a: str, b: str, scenario: Scenario) -> bool:
    """True if nodes a and b share a direct available edge."""
    nodes = scenario.link_nodes
    if a not in nodes or b not in nodes:
        raise ValueError(f"unknown link node: {a if a not in nodes else b}")
    return scenario.link_matrix[nodes.index(a)][nodes.index(b)] == 1


def path_linked(path: list[str], scenario: Scenario) -> bool:
    """True if every consecutive pair in path is directly linked."""
    return all(linked(a, b, scenario) for a, b in zip(path, path[1:]))


def connected_T(bits: tuple[int, ...], scenario: Scenario) -> int:
    """x0 * (l_B*x2 + l_C*x4), also requiring BASE-HILL. 0/1 for feasible bits."""
    if not bits[0] or not linked("BASE", "HILL", scenario):
        return 0
    l_b, l_c = scenario.valley_link_flags
    return bits[0] * (l_b * bits[2] + l_c * bits[4])
