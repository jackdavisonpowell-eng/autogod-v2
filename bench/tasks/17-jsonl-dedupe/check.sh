#!/bin/sh
set -eu
chmod +x run.sh 2>/dev/null || true
[ -f run.sh ] || { echo "FAIL: run.sh missing"; exit 1; }
./run.sh
[ -f deduped.jsonl ] || { echo "FAIL: deduped.jsonl missing"; exit 1; }
python3 - <<'PY'
import json, sys
expected = [{'id': 1, 'name': 'alpha'}, {'id': 2, 'name': 'beta'}, {'id': 3, 'name': 'gamma'}, {'id': 4, 'name': 'delta'}]
lines = [l for l in open("deduped.jsonl").read().splitlines() if l.strip()]
if len(lines) != len(expected):
    print(f"FAIL: expected {len(expected)} lines, got {len(lines)}"); sys.exit(1)
for i, (exp, l) in enumerate(zip(expected, lines)):
    try:
        got = json.loads(l)
    except Exception as e:
        print(f"FAIL: line {i+1} not valid json: {e}"); sys.exit(1)
    if got != exp:
        print(f"FAIL: line {i+1} expected {exp} got {got}"); sys.exit(1)
print("OK")
PY
