#!/bin/sh
set -eu
[ -f output.md ] || { echo "FAIL: output.md missing"; exit 1; }
python3 - <<'PY'
import re, sys
src = open("loose-ends.md").read()
items = re.findall(r'^- \[ \] (.+)$', src, re.M)
seen = []
for it in items:
    if it not in seen:
        seen.append(it)
out_lines = [l for l in open("output.md").read().splitlines() if l.strip()]
if len(out_lines) != len(seen):
    print(f"FAIL: expected {len(seen)} lines, got {len(out_lines)}"); sys.exit(1)
for i, (exp, got) in enumerate(zip(seen, out_lines)):
    expected_line = f"- [ ] {exp}"
    if got.strip() != expected_line:
        print(f"FAIL: line {i+1} expected {expected_line!r} got {got!r}"); sys.exit(1)
print("OK")
PY
