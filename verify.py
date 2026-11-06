"""Run every module's main.py, the way CI does.

Each main.py checks its own claims with assert, so a chapter whose code drifts out of
sync with what its README says fails here.

Usage: python verify.py            # all modules
       python verify.py 03 05      # just these
"""

from __future__ import annotations

import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))


def main() -> int:
    wanted = sys.argv[1:]
    modules = sorted(
        d for d in os.listdir(ROOT)
        if os.path.isfile(os.path.join(ROOT, d, "main.py")) and d[:2].isdigit()
    )
    if wanted:
        modules = [m for m in modules if m[:2] in wanted]
    if not modules:
        print("no modules matched")
        return 2
    # Windows CI consoles are cp1252: make the children print UTF-8 regardless.
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    failed: list[str] = []
    for m in modules:
        t0 = time.perf_counter()
        p = subprocess.run(
            [sys.executable, os.path.join(ROOT, m, "main.py")],
            cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", timeout=300,
        )
        dt = time.perf_counter() - t0
        if p.returncode == 0:
            print(f"PASS  {m}  ({dt:.1f}s)")
        else:
            failed.append(m)
            print(f"FAIL  {m}  ({dt:.1f}s)")
            print(p.stdout[-2000:])
            print(p.stderr[-3000:])
    print(f"\n{len(modules) - len(failed)}/{len(modules)} modules verified")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
