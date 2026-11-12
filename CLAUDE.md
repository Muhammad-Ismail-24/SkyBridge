# CLAUDE.md — SkyBridge session rules

Specs: `architecture.md` (source of truth), `work_division.md`. Do not read any `.docx`.

## 1. Who I work for and file ownership
I am working for **Ismail**. He owns ONLY:
- `src/scenario.py`, `src/network.py`, `src/evaluate.py`, `src/pipeline.py`
- `run.py`, `data/*.json`
- `tests/test_network.py`, `tests/test_constraints.py`
- `tests/test_pipeline.py` (jointly with Sufiyan)

NEVER edit `src/model.py`, `src/quantum.py`, `src/baseline.py` or their tests (Zaheen's).
NEVER edit `scripts/`, `README.md`, `app.py`, `report/` (Sufiyan's).

## 2. Repository layout (mandatory)
- The tree in `architecture.md` section 6 is mandatory. No other top-level folders, no moved files.
- Generated run output goes ONLY in `artifacts/runs/`.

## 3. Variable order (everywhere)
Bits indexed `[x0..x7]` = `A_H, A_N, B_V, B_Delivery, C_V, C_E, D_Delivery, D_S`.
Bitstrings are tuples of 0/1, length 8.

## 4. Agreed decisions
- A missing radio link does NOT make a plan infeasible. It only removes the connectivity bonus:
  `connected_T = x0 * (l_B*x2 + l_C*x4)`.
- Battery rule: `e_i + reserve <= battery[drone]` (less-than-or-equal). Reserve = 15.
- `load_scenario(name, policy)`: name in {`base`, `relay_failure`, `shadow_block`};
  policy in {`mission_first`, `balanced`, `coverage_first`}.
- Policy W: mission_first=3, balanced=22, coverage_first=35. alpha=0.05.
- Run file name: `artifacts/runs/<scenario>.json` for (balanced, seed 42);
  otherwise `<scenario>__<policy>__seed<N>.json`.
- Scenario exposes `conflict_pairs` and `forbidden_indices`.
  `is_feasible` must re-derive feasibility from raw fields (drones, battery, energies,
  disabled drones) and must NOT import `src/model.py`.

## 5. Honesty rules
- NEVER fabricate quantum results, scores, timings or filenames.
- NEVER substitute the exact solver's answer for a quantum result.
- If Qiskit did not run: `ran_qiskit` = false and quantum fields = null.
- Mark synthetic data as illustrative.

## 6. Reporting
After each work package, update `artifacts/COMPLETION_REPORT.md` using the exact headings
in `architecture.md` section 9. Record real commands run and real results only.

## 7. Git
- No `git commit` or `git push` unless Ismail explicitly asks.
- Never commit after 23:59 PKT on 12 Nov 2026.

## 8. Code style
- Python 3.11, dataclasses, standard library plus numpy and pytest only in Ismail's modules.
- Type hints and short docstrings. No extra abstractions.

## 9. Replies
Terse: state what changed and the test result, nothing else.
