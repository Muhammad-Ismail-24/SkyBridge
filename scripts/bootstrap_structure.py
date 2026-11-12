#!/usr/bin/env python3
"""Non-destructively create canonical SkyBridge directories (no fake code/results)."""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
DIRECTORIES = [
    'src','data','tests','scripts','artifacts','artifacts/runs',
    'artifacts/figures','report','.github','.github/workflows'
]

def main() -> None:
    for name in DIRECTORIES:
        folder = ROOT / name
        folder.mkdir(parents=True, exist_ok=True)
        # Git can't store empty directories; markers do not mean work was completed.
        if name not in ('.github','.github/workflows','scripts'):
            marker=folder/'.gitkeep'
            if not any(folder.iterdir()):
                marker.touch(exist_ok=True)
    phase=ROOT/'.skybridge-phase'
    if not phase.exists():
        phase.write_text('scaffold\n',encoding='utf-8')
    print('Canonical SkyBridge directories present. No implementation or results were created.')

if __name__ == '__main__':
    main()
