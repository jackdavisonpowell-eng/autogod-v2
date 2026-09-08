#!/bin/sh
set -eu
[ -f stale.md ] || { echo "FAIL: stale.md missing"; exit 1; }
python3 - <<'PY'
import sys
expected = ['- s5.md (updated: 2026-01-15)', '- s2.md (updated: 2026-06-01)', '- s3.md (updated: 2026-08-01)']
got = [l.strip() for l in open("stale.md").read().splitlines() if l.strip()]
if got != expected:
    print(f"FAIL: expected {expected} got {got}"); sys.exit(1)
print("OK")
PY
