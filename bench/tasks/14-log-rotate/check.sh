#!/bin/sh
set -eu
chmod +x run.sh 2>/dev/null || true
[ -f run.sh ] || { echo "FAIL: run.sh missing"; exit 1; }
./run.sh
python3 - <<'PY'
import sys
expect = {
    "logs/app.log": "",
    "logs/app.log.1": "current log content\n",
    "logs/app.log.2": "old log 1\n",
    "logs/app.log.3": "old log 2\n",
}
for fn, content in expect.items():
    try:
        got = open(fn).read()
    except FileNotFoundError:
        print(f"FAIL: {fn} missing"); sys.exit(1)
    if got != content:
        print(f"FAIL: {fn} expected {content!r} got {got!r}"); sys.exit(1)
print("OK")
PY
