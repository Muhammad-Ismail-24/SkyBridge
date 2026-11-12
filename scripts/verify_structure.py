#!/usr/bin/env python3
"""Enforce SkyBridge's canonical repository layout.

Usage from repository root:
  python scripts/verify_structure.py --phase scaffold --strict
  python scripts/verify_structure.py --phase implementation --strict
  python scripts/verify_structure.py --phase submission --strict
  python scripts/verify_structure.py --phase tracked --strict

Structural compliance is not a claim that QAOA, tests, or external links work.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import zipfile
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
STAGES = {"scaffold": 0, "implementation": 1, "submission": 2}

CANONICAL_DIRS = (
    'src', 'data', 'tests', 'scripts', 'artifacts', 'artifacts/runs',
    'artifacts/figures', 'report', '.github', '.github/workflows'
)

REQUIRED = {
    'scaffold': (
        'architecture.md', 'work_division.md', '.skybridge-phase',
        'scripts/verify_structure.py', 'scripts/bootstrap_structure.py',
        '.github/workflows/structure.yml',
    ),
    'implementation': (
        'README.md', 'requirements.txt', 'run.py',
        'src/scenario.py', 'src/network.py', 'src/model.py',
        'src/quantum.py', 'src/baseline.py', 'src/evaluate.py',
        'src/pipeline.py', 'data/base.json',
        'tests/test_model.py', 'tests/test_exact.py',
        'tests/test_network.py', 'tests/test_constraints.py',
        'tests/test_pipeline.py',
    ),
    'submission': (
        'scripts/generate_report.py', 'scripts/verify_submission.py',
        'artifacts/COMPLETION_REPORT.md',
        'report/SkyBridge_Hackathon_Report.docx',
    ),
}

TOP_ALLOWED = {
    'architecture.md', 'work_division.md', '.skybridge-phase', '.gitignore',
    '.gitattributes', '.editorconfig', 'README.md', 'requirements.txt',
    'run.py', 'app.py', 'pyproject.toml', 'uv.lock', '.python-version',
    'LICENSE', 'LICENSE.md', 'Makefile', 'src', 'data', 'tests',
    'scripts', 'artifacts', 'report', '.github',
}
TOP_IGNORED = {'.git', '.venv', 'venv', '__pycache__', '.pytest_cache',
               '.mypy_cache', '.ruff_cache', '.idea', '.vscode', '.tox', 'htmlcov'}
FILE_EXTENSIONS = {
    'src': {'.py', '.pyi'},
    'tests': {'.py'},
    'data': {'.json'},
    'scripts': {'.py'},
}


def bad_file_locations(root: Path) -> list[str]:
    errors: list[str] = []
    for child in root.iterdir():
        if child.name in TOP_IGNORED or child.name.startswith('.tmp'):
            continue
        if child.name not in TOP_ALLOWED:
            errors.append(f'Unexpected top-level entry: {child.name!r}; place it in canonical directory')
    for group, extensions in FILE_EXTENSIONS.items():
        directory = root / group
        if not directory.exists():
            continue
        for path in directory.rglob('*'):
            if any(part in {'__pycache__','.pytest_cache'} for part in path.relative_to(directory).parts):
                continue
            if path.is_dir():
                errors.append(f'Unexpected nested directory in flat {group}/ layout: {path.relative_to(root)}')
            elif path.is_file() and path.name != '.gitkeep' and path.suffix.lower() not in extensions:
                errors.append(f'Wrong file type/location: {path.relative_to(root)} (allowed: {sorted(extensions)})')
    for subdir, extensions in [('artifacts/runs',{'.json'}),
                               ('artifacts/figures',{'.png','.svg','.jpg','.jpeg','.webp'}),
                               ('report',{'.docx'})]:
        directory = root / subdir
        if directory.exists():
            for p in directory.rglob('*'):
                if p.is_file() and p.name != '.gitkeep' and p.suffix.lower() not in extensions:
                    errors.append(f'Wrong generated-artifact location or type: {p.relative_to(root)}')
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=[*STAGES, 'tracked'], default='tracked')
    parser.add_argument('--strict', action='store_true', help='Reject out-of-contract top-level paths and file types')
    parser.add_argument('--root', type=Path, default=BASE, help='Repository root (defaults to this script\'s grandparent)')
    args = parser.parse_args(argv)
    root = args.root.resolve()
    errors: list[str] = []
    phase_path = root / '.skybridge-phase'
    declared = phase_path.read_text(encoding='utf-8').strip() if phase_path.is_file() else None
    if declared not in STAGES:
        errors.append('.skybridge-phase must contain exactly: scaffold, implementation, or submission')
    phase = declared if args.phase == 'tracked' else args.phase
    if phase not in STAGES:
        errors.append('No valid verification phase selected')
    else:
        for subdir in CANONICAL_DIRS:
            if not (root/subdir).is_dir():
                errors.append(f'Missing canonical directory: {subdir}/')
        for stage, paths in REQUIRED.items():
            if STAGES[stage] <= STAGES[phase]:
                for path in paths:
                    item = root/path
                    if not item.is_file():
                        errors.append(f'Missing required {stage} file: {path}')
                    elif item.stat().st_size == 0:
                        errors.append(f'Empty required file: {path}')
        if STAGES[phase] >= STAGES['implementation'] and (root/'data/base.json').is_file():
            try:
                json.loads((root/'data/base.json').read_text(encoding='utf-8'))
            except (ValueError, UnicodeError) as exc:
                errors.append(f'data/base.json is not valid JSON: {exc}')
        if phase == 'submission':
            run_dir = root/'artifacts/runs'
            runs = sorted(run_dir.glob('*.json')) if run_dir.is_dir() else []
            if not runs:
                errors.append('No real run JSON found under artifacts/runs/ (required for submission)')
            for run in runs:
                try:
                    data = json.loads(run.read_text(encoding='utf-8'))
                    if not isinstance(data,dict) or not {'scenario','quantum','exact','comparison'} <= data.keys():
                        errors.append(f'Invalid result record fields: {run.relative_to(root)}')
                except (ValueError,UnicodeError) as exc:
                    errors.append(f'Invalid result JSON {run.relative_to(root)}: {exc}')
            fig_dir=root/'artifacts/figures'
            figures = [p for p in fig_dir.iterdir() if p.suffix.lower() in {'.png','.svg','.jpg','.jpeg','.webp'}] if fig_dir.is_dir() else []
            if not figures:
                errors.append('Architecture/other figure missing: artifacts/figures/')
            docx=root/'report/SkyBridge_Hackathon_Report.docx'
            if docx.is_file() and (not zipfile.is_zipfile(docx) or docx.stat().st_size < 1000):
                errors.append('Report must be an actual nonempty .docx file')
            report=root/'artifacts/COMPLETION_REPORT.md'
            if report.is_file() and len(report.read_text(encoding='utf-8').strip()) < 200:
                errors.append('Completion report too short to be a meaningful progress record')
        if args.strict:
            errors.extend(bad_file_locations(root))
    if args.phase == 'tracked' and declared:
        print(f'SkyBridge tracked phase: {declared}')
    if errors:
        print('SKYBRIDGE STRUCTURE CHECK: FAIL')
        for error in errors:
            print(f'  [X] {error}')
        return 1
    print(f'SKYBRIDGE STRUCTURE CHECK: PASS ({phase}, strict={args.strict})')
    print('Note: passing structure checks does NOT validate quantum execution, mathematical correctness, or deliverable quality.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
