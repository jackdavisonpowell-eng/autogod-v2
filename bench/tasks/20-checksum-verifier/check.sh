#!/bin/sh
set -eu
chmod +x run.sh 2>/dev/null || true
[ -f run.sh ] || { echo "FAIL: run.sh missing"; exit 1; }
./run.sh >run.out 2>/dev/null
python3 - <<'PY'
import sys
expected = ['a.txt: OK', 'b.txt: OK', 'c.txt: MISMATCH']
got = [l.strip() for l in open("run.out").read().splitlines() if l.strip()]
if got != expected:
    print(f"FAIL: expected {expected} got {got}"); sys.exit(1)
print("OK")
PY
