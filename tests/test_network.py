"""Network / connectivity tests (synthetic, illustrative links)."""
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.network import connected_T, linked, path_linked  # noqa: E402
from src.scenario import load_scenario  # noqa: E402

BASE = load_scenario("base")
SHADOW = load_scenario("shadow_block")


def test_linked_edges():
    assert linked("BASE", "HILL", BASE) and linked("HILL", "BASE", BASE)
    assert not linked("BASE", "TEAM", BASE)
    assert not linked("HILL", "VALLEY_B", SHADOW)


def test_linked_unknown_node():
    with pytest.raises(ValueError, match="unknown link node"):
        linked("BASE", "MOON", BASE)


def test_path_linked():
    assert path_linked(["BASE", "HILL", "VALLEY_B", "TEAM"], BASE)
    assert not path_linked(["BASE", "HILL", "VALLEY_B", "TEAM"], SHADOW)
    assert path_linked(["BASE", "HILL", "VALLEY_C", "TEAM"], SHADOW)


def test_empty_state_not_connected():
    assert connected_T((0,) * 8, BASE) == 0


def test_hill_missing():
    assert connected_T((0, 0, 1, 0, 0, 0, 0, 0), BASE) == 0
    assert connected_T((0, 0, 0, 0, 1, 0, 0, 0), BASE) == 0


def test_valley_missing():
    assert connected_T((1, 0, 0, 0, 0, 0, 0, 0), BASE) == 0


def test_connected_plans():
    assert connected_T((1, 0, 1, 0, 0, 0, 0, 0), BASE) == 1
    assert connected_T((1, 0, 0, 0, 1, 0, 0, 0), BASE) == 1


def test_shadow_block():
    assert connected_T((1, 0, 1, 0, 0, 0, 0, 0), SHADOW) == 0
    assert connected_T((1, 0, 0, 0, 1, 0, 0, 0), SHADOW) == 1


def test_base_hill_link_required():
    m = [row[:] for row in BASE.link_matrix]
    m[0][1] = m[1][0] = 0
    cut = replace(BASE, link_matrix=m)
    assert connected_T((1, 0, 1, 0, 0, 0, 0, 0), cut) == 0
