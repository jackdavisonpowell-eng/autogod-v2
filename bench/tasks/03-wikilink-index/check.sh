#!/bin/sh
set -eu
[ -f index.md ] || { echo "FAIL: index.md missing"; exit 1; }
python3 - <<'PY'
import re, glob, sys
targets = set()
for fn in glob.glob("*.md"):
    if fn == "index.md":
        continue
    for m in re.findall(r'\[\[([^\]]+)\]\]', open(fn).read()):
        targets.add(m.split('|')[0].strip())
expected = sorted(targets)
got_lines = [l.strip() for l in open("index.md").read().splitlines() if l.strip()]
got = []
for l in got_lines:
    if not l.startswith('- '):
        print(f"FAIL: bad line {l!r}"); sys.exit(1)
    got.append(l[2:].strip())
if sorted(got) != expected or got != sorted(got):
    print(f"FAIL: expected {expected} got {got}"); sys.exit(1)
print("OK")
PY
