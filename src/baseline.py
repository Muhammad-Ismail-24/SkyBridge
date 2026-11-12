"""Independent exhaustive (exact) baseline for SkyBridge.

Owner: Zaheen. Contract: architecture.md §6, work_division.md Z3.

``solve_exact`` enumerates all 2**n logical assignments and judges each one with
the *original* hard constraints and *true* utility from Ismail's
``src/evaluate.py`` (``is_feasible`` / ``score_feasible``). It never reads QAOA
samples, quantum parameters or QUBO energies, so it is an independent check on
the quantum branch.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

from src.model import all_bitstrings, model_inputs_from_scenario

UTILITY_TIE_TOL = 1e-9
TIE_BREAKER = (
    "highest total_utility; ties (|ΔU| <= 1e-9) broken by the lexicographically "
    "smallest canonical tuple (x0, ..., x7)"
)

FeasibleFn = Callable[[tuple[int, ...], Any], bool]
ScoreFn = Callable[[tuple[int, ...], Any], dict]


def _default_evaluator() -> tuple[FeasibleFn, ScoreFn]:
    try:
        from src.evaluate import is_feasible, score_feasible  # Ismail-owned
    except ImportError as exc:  # pragma: no cover - depends on teammate delivery
        raise ImportError(
            "src/evaluate.py (Ismail) is required for is_feasible/score_feasible; "
            "pass is_feasible= and score_feasible= explicitly until it lands"
        ) from exc
    return is_feasible, score_feasible


def resolve_evaluator(
    is_feasible: FeasibleFn | None, score_feasible: ScoreFn | None
) -> tuple[FeasibleFn, ScoreFn]:
    if is_feasible is None or score_feasible is None:
        default_f, default_s = _default_evaluator()
        is_feasible = is_feasible or default_f
        score_feasible = score_feasible or default_s
    return is_feasible, score_feasible


def total_utility(breakdown: dict) -> float:
    if "total_utility" not in breakdown:
        raise KeyError("score_feasible must return a 'total_utility' entry")
    return float(breakdown["total_utility"])


@dataclass(frozen=True)
class ExactResult:
    best_bits: tuple[int, ...] | None
    utility: float | None
    breakdown: dict | None
    enumerated_states: int
    feasible_states: int
    infeasible_states: int
    tied_optimal_bits: tuple[tuple[int, ...], ...]
    tie_breaker: str
    elapsed_seconds: float
    feasible_ranking: tuple[tuple[tuple[int, ...], float], ...] = field(repr=False, default=())

    @property
    def status(self) -> str:
        return "optimal" if self.best_bits is not None else "no_feasible_assignment"

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "best_bits": list(self.best_bits) if self.best_bits is not None else None,
            "utility": self.utility,
            "breakdown": self.breakdown,
            "enumerated_states": self.enumerated_states,
            "feasible_states": self.feasible_states,
            "infeasible_states": self.infeasible_states,
            "tied_optimal_bits": [list(b) for b in self.tied_optimal_bits],
            "tie_breaker": self.tie_breaker,
            "elapsed_seconds": self.elapsed_seconds,
        }


def solve_exact(
    scenario: Any,
    *,
    is_feasible: FeasibleFn | None = None,
    score_feasible: ScoreFn | None = None,
) -> ExactResult:
    """Exhaustively search every assignment; return the best feasible one.

    The optional ``is_feasible`` / ``score_feasible`` keywords exist only so tests
    can inject an evaluator; by default Ismail's ``src.evaluate`` is used.
    """
    feasible_fn, score_fn = resolve_evaluator(is_feasible, score_feasible)
    n = len(model_inputs_from_scenario(scenario).labels)

    t0 = time.perf_counter()
    enumerated = 0
    ranking: list[tuple[tuple[int, ...], float, dict]] = []
    for bits in all_bitstrings(n):
        enumerated += 1
        if not feasible_fn(bits, scenario):
            continue
        breakdown = score_fn(bits, scenario)
        ranking.append((bits, total_utility(breakdown), breakdown))
    elapsed = time.perf_counter() - t0

    # Python sort is stable and tuples compare lexicographically -> deterministic.
    ranking.sort(key=lambda r: (-r[1], r[0]))
    if ranking:
        best_bits, best_u, best_breakdown = ranking[0]
        ties = tuple(b for b, u, _ in ranking if abs(u - best_u) <= UTILITY_TIE_TOL)
        best_bits = min(ties)
        best_breakdown = next(bd for b, _, bd in ranking if b == best_bits)
        best_u = total_utility(best_breakdown)
    else:
        best_bits, best_u, best_breakdown, ties = None, None, None, ()

    return ExactResult(
        best_bits=best_bits,
        utility=best_u,
        breakdown=best_breakdown,
        enumerated_states=enumerated,
        feasible_states=len(ranking),
        infeasible_states=enumerated - len(ranking),
        tied_optimal_bits=ties,
        tie_breaker=TIE_BREAKER,
        elapsed_seconds=elapsed,
        feasible_ranking=tuple((b, u) for b, u, _ in ranking),
    )


def compare_results(exact: ExactResult, quantum_utility: float | None) -> dict:
    """Quantum-vs-exact gap on the SAME true utility (architecture.md §7)."""
    notes: list[str] = []
    if exact.utility is None:
        return {
            "absolute_gap": None,
            "relative_gap_pct": None,
            "matches_exact_optimum": None,
            "notes": ["exact search found no feasible assignment"],
        }
    if quantum_utility is None:
        return {
            "absolute_gap": None,
            "relative_gap_pct": None,
            "matches_exact_optimum": False,
            "notes": ["QAOA produced no feasible sample; gap undefined"],
        }
    gap = exact.utility - quantum_utility
    if abs(gap) <= UTILITY_TIE_TOL:
        gap = 0.0
    if gap < 0:
        notes.append("quantum utility exceeds exact optimum: evaluator inconsistency, investigate")
    if abs(exact.utility) > UTILITY_TIE_TOL:
        rel = 100.0 * gap / abs(exact.utility)
    else:
        rel = None
        notes.append("exact optimum is zero; relative gap undefined")
    return {
        "absolute_gap": gap,
        "relative_gap_pct": rel,
        "matches_exact_optimum": gap == 0.0,
        "notes": notes,
    }


def rank_of_utility(exact: ExactResult, utility: float | None) -> int | None:
    """1-based rank of ``utility`` among distinct feasible utilities (1 = optimal)."""
    if utility is None or not exact.feasible_ranking:
        return None
    distinct: list[float] = []
    for _, u in exact.feasible_ranking:
        if not distinct or abs(distinct[-1] - u) > UTILITY_TIE_TOL:
            distinct.append(u)
    for k, u in enumerate(distinct, start=1):
        if utility >= u - UTILITY_TIE_TOL:
            return k
    return len(distinct) + 1


def bits_label(bits: Sequence[int] | None, ordering: Sequence[str]) -> list[str]:
    return [] if bits is None else [name for name, b in zip(ordering, bits) if b]
