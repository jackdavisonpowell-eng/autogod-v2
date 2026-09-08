#!/bin/sh
set -eu
[ -f output.md ] || { echo "FAIL: output.md missing"; exit 1; }
python3 - <<'PY'
import re, sys
out = open("output.md").read()
expected = {
    "tomorrow": "2026-09-09",
    "in 3 days": "2026-09-11",
    "yesterday": "2026-09-07",
    "in 5 days": "2026-09-13",
    "next week": "2026-09-15",
}
for phrase, date in expected.items():
    if date not in out:
        print(f"FAIL: missing {date} for {phrase!r}"); sys.exit(1)
print("OK")
PY
