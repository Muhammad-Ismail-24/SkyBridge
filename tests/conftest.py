"""Shared pytest fixtures.

Uses Ismail's ``src.scenario`` / ``src.evaluate`` when present; otherwise falls
back to the test-only transcription of architecture.md §4 in
``tests/reference_contract.py`` (see that file's docstring).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests import reference_contract as ref  # noqa: E402


def _real_contract():
    try:
        from src.evaluate import is_feasible, score_feasible
        from src.scenario import load_scenario
    except ImportError:
        return None
    return load_scenario, is_feasible, score_feasible


REAL = _real_contract()
CONTRACT_SOURCE = "src.scenario/src.evaluate (Ismail)" if REAL else "tests/reference_contract.py"


@pytest.fixture(scope="session")
def contract():
    """(load(name, policy) -> scenario, is_feasible, score_feasible)."""
    if REAL:
        return REAL
    return (
        lambda name="base", policy="balanced": ref.reference_scenario(name, policy),
        ref.ref_is_feasible,
        ref.ref_score_feasible,
    )


@pytest.fixture(scope="session")
def base_scenario(contract):
    return contract[0]("base", "balanced")


@pytest.fixture(scope="session")
def evaluator(contract):
    return {"is_feasible": contract[1], "score_feasible": contract[2]}


def pytest_report_header(config):
    return f"SkyBridge scenario/evaluator contract source: {CONTRACT_SOURCE}"
