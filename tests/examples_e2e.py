"""Run a Playwright example against the mock line and check it saw the IP change.

    python tests/examples_e2e.py python examples/playwright_rotate.py
    python tests/examples_e2e.py node examples/playwright_rotate.mjs
"""

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(__file__))
import mockproxy  # noqa: E402

server, state, env = mockproxy.start()
cmd = [sys.executable if sys.argv[1] == "python" else sys.argv[1], *sys.argv[2:]]
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
proc = subprocess.run(cmd, env={**os.environ, **env, "PYTHONPATH": os.path.join(root, "src")},
                      capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
print(proc.stdout)
print(proc.stderr[-3000:], file=sys.stderr)
ok = (proc.returncode == 0 and "before: 203.0.113.1" in proc.stdout and "after:  203.0.113.2" in proc.stdout
      and state.rotations == 1)
print("OK" if ok else f"FAILED (exit {proc.returncode}, rotations {state.rotations})")
sys.exit(0 if ok else 1)
