#!/bin/sh
set -eu
[ -f merged.md ] || { echo "FAIL: merged.md missing"; exit 1; }
python3 - <<'PY'
import re, sys

def parse(fn):
    d = {}
    for line in open(fn):
        m = re.match(r'^- ([^:]+):\s*(.+)$', line.strip())
        if m:
            d[m.group(1).strip()] = m.group(2).strip()
    return d

a = parse("note.md")
b = parse("note (conflicted copy).md")
expected = dict(b)
expected.update(a)  # note.md wins on conflict
got = parse("merged.md")
if got != expected:
    print(f"FAIL: expected {expected} got {got}"); sys.exit(1)
print("OK")
PY
