#!/bin/sh
set -eu
[ -x run.sh ] || chmod +x run.sh 2>/dev/null || true
[ -f run.sh ] || { echo "FAIL: run.sh missing"; exit 1; }
OUT=$(./run.sh 2>/dev/null)
python3 - "$OUT" <<'PY'
import json, sys
expected = {'a.txt': 9, 'b.txt': 5}
try:
    got = json.loads(sys.argv[1])
except Exception as e:
    print(f"FAIL: stdout is not valid JSON: {e}"); sys.exit(1)
if got != expected:
    print(f"FAIL: expected {expected} got {got}"); sys.exit(1)
print("OK")
PY
