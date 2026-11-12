"""Constraint tests. Section 1: scenario loader (synthetic, illustrative data)."""
import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.scenario import build_scenario, load_scenario  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "data"


def _raw() -> dict:
    return json.loads((DATA / "base.json").read_text(encoding="utf-8"))


# ---- loader ----
@pytest.mark.parametrize("policy,w", [("mission_first", 3), ("balanced", 22),
                                      ("coverage_first", 35)])
def test_policies_load(policy, w):
    s = load_scenario("base", policy)
    assert s.relay_weight == w and s.policy == policy and s.alpha == 0.05


def test_default_policy_is_balanced():
    assert load_scenario("base").relay_weight == 22


def test_base_values():
    s = load_scenario("base")
    assert [r.index for r in s.roles] == list(range(8))
    assert [r.utility for r in s.roles] == [1, 8, 1, 6, 1, 7, 6, 4]
    assert [r.energy for r in s.roles] == [40, 30, 35, 45, 30, 35, 40, 25]
    assert s.battery == {"A": 85, "B": 80, "C": 60, "D": 55} and s.reserve == 15
    assert s.conflict_pairs == [(0, 1), (2, 3), (4, 5), (6, 7), (2, 4), (3, 6)]
    assert s.forbidden_indices == []  # D role 6: 40+15 == 55 is allowed (<=)
    assert s.valley_link_flags == (1, 1)


def test_failure_forbids_2_and_3():
    s = load_scenario("relay_failure")
    assert set(s.forbidden_indices) == {2, 3} and s.disabled_drones == {"B"}


def test_shadow_block_flags():
    s = load_scenario("shadow_block")
    assert s.valley_link_flags == (0, 1)
    assert load_scenario("base").valley_link_flags == (1, 1)  # base not mutated


def test_to_dict_json_serialisable():
    d = json.loads(json.dumps(load_scenario("base").to_dict()))
    assert d["relay_weight"] == 22 and len(d["roles"]) == 8


# ---- bad inputs ----
def test_unknown_scenario():
    with pytest.raises(ValueError, match="unknown scenario 'nope'"):
        load_scenario("nope")


def test_unknown_policy():
    with pytest.raises(ValueError, match="unknown policy 'greedy'"):
        load_scenario("base", "greedy")


def test_missing_field():
    raw = _raw(); del raw["battery"]
    with pytest.raises(ValueError, match="missing field 'battery'"):
        build_scenario(raw, "base", "balanced", 22)


def test_wrong_roles_length():
    raw = _raw(); raw["roles"] = raw["roles"][:7]
    with pytest.raises(ValueError, match="'roles' must have length 8, got 7"):
        build_scenario(raw, "base", "balanced", 22)


def test_non_symmetric_matrix():
    raw = _raw(); raw["link_matrix"][0][1] = 0
    with pytest.raises(ValueError, match="not symmetric"):
        build_scenario(raw, "base", "balanced", 22)


def test_wrong_matrix_size():
    raw = _raw(); raw["link_matrix"] = raw["link_matrix"][:4]
    with pytest.raises(ValueError, match="5x5"):
        build_scenario(raw, "base", "balanced", 22)


def test_negative_values():
    raw = _raw(); raw["roles"][0]["energy"] = -1
    with pytest.raises(ValueError, match="energy must be non-negative"):
        build_scenario(raw, "base", "balanced", 22)
    raw = copy.deepcopy(_raw()); raw["reserve"] = -5
    with pytest.raises(ValueError, match="reserve must be non-negative"):
        build_scenario(raw, "base", "balanced", 22)


def test_swapped_role_order_rejected():
    raw = _raw()
    raw["roles"][2], raw["roles"][3] = raw["roles"][3], raw["roles"][2]
    with pytest.raises(ValueError, match=r"roles\[2\] must be drone/kind"):
        build_scenario(raw, "base", "balanced", 22)


def test_unknown_disabled_drone():
    raw = _raw(); raw["disabled_drones"] = ["Z"]
    with pytest.raises(ValueError, match="not a known drone"):
        build_scenario(raw, "base", "balanced", 22)


# ==== Section 2: hard constraints and scoring ====
import itertools  # noqa: E402
from dataclasses import replace  # noqa: E402

from src.evaluate import is_feasible, score_degraded, score_feasible  # noqa: E402

B = load_scenario("base")
F = load_scenario("relay_failure")
Z = (0,) * 8


def _bits(*on):
    return tuple(1 if i in on else 0 for i in range(8))


def test_empty_state_feasible_zero():
    s = score_feasible(Z, B)
    assert s["feasible"] and s["total_utility"] == 0 and s["connected_teams"] == 0


@pytest.mark.parametrize("on", [(0, 1), (2, 3), (4, 5), (6, 7)])
def test_two_roles_one_drone(on):
    assert not is_feasible(_bits(*on), B)


def test_both_valley_relays():
    assert not is_feasible(_bits(2, 4), B)
    assert not is_feasible(_bits(0, 2, 4), B)


def test_both_deliveries():
    assert not is_feasible(_bits(3, 6), B)


def test_connected_plan_scores_bonus():
    s = score_feasible(_bits(0, 2), B)
    assert s["feasible"] and s["connected_teams"] == 1 and s["connectivity_bonus"] == 22


def test_hill_missing_no_bonus():
    s = score_feasible(_bits(2), B)
    assert s["connected_teams"] == 0 and s["connectivity_bonus"] == 0


def test_shadow_block_feasible_but_no_bonus():
    sh = load_scenario("shadow_block")
    assert score_feasible(_bits(0, 2), sh)["connected_teams"] == 0
    assert score_feasible(_bits(0, 2), sh)["feasible"]  # missing link != infeasible
    assert score_feasible(_bits(0, 4), sh)["connected_teams"] == 1


@pytest.mark.parametrize("i", [2, 3])
def test_b_failure_forces_zero(i):
    assert is_feasible(_bits(i), B)
    assert not is_feasible(_bits(i), F)


def test_d_delivery_battery_boundary():
    assert is_feasible(_bits(6), B)  # 40 + 15 == 55
    assert not is_feasible(_bits(6), replace(B, reserve=16))


def test_score_terms_add_up():
    s = score_feasible(_bits(0, 2, 5, 6), B)
    assert s["total_utility"] == s["mission_score"] - s["energy_penalty"] + s["connectivity_bonus"]
    assert s["total_utility"] == pytest.approx(29.5)


def test_infeasible_has_no_number():
    s = score_feasible(_bits(0, 1), B)
    assert s["feasible"] is False and s["total_utility"] is None


@pytest.mark.parametrize("bad", [(0,) * 7, (0,) * 9, (2,) + (0,) * 7,
                                 (True,) + (0,) * 7, "00000000", None])
def test_bad_input(bad):
    assert is_feasible(bad, B) is False
    assert score_feasible(bad, B)["feasible"] is False


def test_score_degraded_b_failure():
    d = score_degraded(_bits(0, 2, 5, 6), "B", B)
    assert d["lost_roles"] == [2] and d["connectivity_lost"] is True
    assert d["bits"] == list(_bits(0, 5, 6)) and d["feasible"]
    assert d["connected_teams"] == 0 and d["total_utility"] == pytest.approx(8.25)


def test_score_degraded_unaffected():
    d = score_degraded(_bits(0, 4), "B", B)
    assert d["lost_roles"] == [] and d["connectivity_lost"] is False


def test_score_degraded_unknown_drone():
    with pytest.raises(ValueError, match="unknown drone"):
        score_degraded(Z, "Q", B)


# ==== Section 3: independent 256-state brute force ====
def _raw_file(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def _brute(file, policy, cut_hill_valley_b=False):
    """Hand-coded constraints/utility straight from JSON (no src.evaluate)."""
    raw = _raw_file(file)
    if cut_hill_valley_b:  # shadow_block = base with the HILL--VALLEY_B edge removed
        n_ = raw["link_nodes"]
        i_, j_ = n_.index("HILL"), n_.index("VALLEY_B")
        raw["link_matrix"][i_][j_] = raw["link_matrix"][j_][i_] = 0
    w = _raw_file("policy_presets.json")[policy]
    v = [r["utility"] for r in raw["roles"]]
    e = [r["energy"] for r in raw["roles"]]
    d = [r["drone"] for r in raw["roles"]]
    m, n = raw["link_matrix"], raw["link_nodes"]
    edge = lambda a, b: m[n.index(a)][n.index(b)]  # noqa: E731
    lb = edge("BASE", "HILL") * edge("HILL", "VALLEY_B") * edge("VALLEY_B", "TEAM")
    lc = edge("BASE", "HILL") * edge("HILL", "VALLEY_C") * edge("VALLEY_C", "TEAM")
    feas, best, best_u = set(), None, None
    for x in itertools.product((0, 1), repeat=8):
        if x[0] + x[1] > 1 or x[2] + x[3] > 1 or x[4] + x[5] > 1 or x[6] + x[7] > 1:
            continue
        if x[2] + x[4] > 1 or x[3] + x[6] > 1:
            continue
        if any(x[i] and (d[i] in raw["disabled_drones"]
                         or e[i] + raw["reserve"] > raw["battery"][d[i]]) for i in range(8)):
            continue
        feas.add(x)
        u = sum((v[i] - raw["alpha"] * e[i]) * x[i] for i in range(8)) + w * x[0] * (lb * x[2] + lc * x[4])
        if best_u is None or u > best_u + 1e-9:
            best, best_u = x, u
    return feas, best, best_u


GOLDEN = [
    ("base", "base.json", "balanced", 63, (1, 0, 1, 0, 0, 1, 1, 0), 29.5),
    ("base", "base.json", "mission_first", 63, (0, 1, 0, 1, 0, 1, 0, 1), 18.25),
    ("relay_failure", "relay_failure.json", "balanced", 27, (1, 0, 0, 0, 1, 0, 1, 0), 24.5),
    ("relay_failure", "relay_failure.json", "mission_first", 27, (0, 1, 0, 0, 0, 1, 1, 0), 15.75),
    ("base", "base.json", "coverage_first", 63, (1, 0, 1, 0, 0, 1, 1, 0), 42.5),
    ("relay_failure", "relay_failure.json", "coverage_first", 27, (1, 0, 0, 0, 1, 0, 1, 0), 37.5),
]


@pytest.mark.parametrize("name,file,policy,n_feas,best_bits,best_u", GOLDEN)
def test_brute_force_golden(name, file, policy, n_feas, best_bits, best_u):
    feas, best, u = _brute(file, policy)
    assert len(feas) == n_feas and best == best_bits and u == pytest.approx(best_u)
    s = load_scenario(name, policy)
    all_x = list(itertools.product((0, 1), repeat=8))
    assert {x for x in all_x if is_feasible(x, s)} == feas
    scores = {x: score_feasible(x, s)["total_utility"] for x in feas}
    top = max(scores.values())
    assert top == pytest.approx(best_u)
    assert [x for x, t in scores.items() if abs(t - top) < 1e-9] == [best_bits]  # unique optimum
    for x in all_x:
        if x not in feas:
            assert score_feasible(x, s)["total_utility"] is None



@pytest.mark.parametrize("policy", ["mission_first", "balanced", "coverage_first"])
def test_brute_force_shadow_block(policy):
    """shadow_block checked against the independent in-test brute force (no remembered numbers)."""
    feas, best, best_u = _brute("base.json", policy, cut_hill_valley_b=True)
    s = load_scenario("shadow_block", policy)
    all_x = list(itertools.product((0, 1), repeat=8))
    assert {x for x in all_x if is_feasible(x, s)} == feas
    scores = {x: score_feasible(x, s)["total_utility"] for x in feas}
    top = max(scores.values())
    assert top == pytest.approx(best_u)
    assert [x for x, t in scores.items() if abs(t - top) < 1e-9] == [best]
    for x in feas:  # every plan scored the same by the hand-coded formula
        assert scores[x] == pytest.approx(_brute_u(x, "base.json", policy, True))


def _brute_u(x, file, policy, cut):
    raw = _raw_file(file)
    n, m = raw["link_nodes"], raw["link_matrix"]
    if cut:
        i, j = n.index("HILL"), n.index("VALLEY_B")
        m[i][j] = m[j][i] = 0
    edge = lambda a, b: m[n.index(a)][n.index(b)]  # noqa: E731
    lb = edge("BASE", "HILL") * edge("HILL", "VALLEY_B") * edge("VALLEY_B", "TEAM")
    lc = edge("BASE", "HILL") * edge("HILL", "VALLEY_C") * edge("VALLEY_C", "TEAM")
    w = _raw_file("policy_presets.json")[policy]
    return (sum((r["utility"] - raw["alpha"] * r["energy"]) * xi for r, xi in zip(raw["roles"], x))
            + w * x[0] * (lb * x[2] + lc * x[4]))


def test_score_degraded_on_post_failure_scenario():
    """Regression: passing relay_failure (B already disabled) must still report
    the pre-failure connectivity as lost."""
    rf = load_scenario("relay_failure", "balanced")
    d = score_degraded((1, 0, 1, 0, 0, 1, 1, 0), "B", rf)
    assert d["connectivity_lost"] is True and d["lost_roles"] == [2]
