#!/bin/sh
set -eu
python3 - <<'PY'
import re, glob, sys
bad = 0
for fn in glob.glob("*.md"):
    text = open(fn).read()
    if re.search(r'\bold-tag\b', text):
        print(f"FAIL: {fn} still contains old-tag"); bad = 1
if bad:
    sys.exit(1)
new_count = sum(len(re.findall(r'\bnew-tag\b', open(fn).read())) for fn in glob.glob("*.md"))
if new_count < 4:
    print(f"FAIL: expected at least 4 new-tag occurrences, got {new_count}"); sys.exit(1)
one = open("one.md").read()
if "misc" not in one:
    print("FAIL: one.md lost the misc tag"); sys.exit(1)
two = open("two.md").read()
if "keep-tag" not in two:
    print("FAIL: two.md lost keep-tag"); sys.exit(1)
print("OK")
PY
