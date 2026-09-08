#!/bin/sh
set -eu
[ -f summary.md ] || { echo "FAIL: summary.md missing"; exit 1; }
python3 - <<'PY'
import re, sys
max_line = 29
journal_lines = open("journal.md").read().splitlines()
bullets = [l for l in open("summary.md").read().splitlines() if l.strip().startswith('-')]
if len(bullets) != 5:
    print(f"FAIL: expected exactly 5 bullets, got {len(bullets)}"); sys.exit(1)
for b in bullets:
    m = re.search(r'\(line (\d+)\)\s*$', b.strip())
    if not m:
        print(f"FAIL: bullet missing trailing (line N) citation: {b!r}"); sys.exit(1)
    n = int(m.group(1))
    if not (1 <= n <= max_line):
        print(f"FAIL: line number {n} out of range 1..{max_line}"); sys.exit(1)
    if not journal_lines[n-1].strip():
        print(f"FAIL: cited line {n} is blank in journal.md"); sys.exit(1)
print("OK")
PY
