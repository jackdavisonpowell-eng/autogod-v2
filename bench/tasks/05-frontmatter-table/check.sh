#!/bin/sh
set -eu
[ -f table.md ] || { echo "FAIL: table.md missing"; exit 1; }
python3 - <<'PY'
import re, sys
expected = [('alpha-project', 'project'), ('bravo-reference', 'reference'), ('charlie-feedback', 'feedback'), ('delta-project', 'project'), ('echo-user', 'user'), ('foxtrot-reference', 'reference'), ('golf-project', 'project'), ('hotel-feedback', 'feedback')]
lines = [l for l in open("table.md").read().splitlines() if l.strip().startswith('|')]
rows = []
for l in lines[2:]:  # skip header + separator
    cells = [c.strip() for c in l.strip().strip('|').split('|')]
    if len(cells) >= 2:
        rows.append((cells[0], cells[1]))
if rows != expected:
    print(f"FAIL: expected {expected} got {rows}"); sys.exit(1)
print("OK")
PY
