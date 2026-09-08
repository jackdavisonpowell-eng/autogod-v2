#!/bin/sh
set -eu
[ -f freq.md ] || { echo "FAIL: freq.md missing"; exit 1; }
python3 - <<'PY'
import sys
expected = ['red: 4', 'blue: 3', 'green: 2', 'yellow: 2']
got = [l.strip() for l in open("freq.md").read().splitlines() if l.strip()]
if got != expected:
    print(f"FAIL: expected {expected} got {got}"); sys.exit(1)
print("OK")
PY
