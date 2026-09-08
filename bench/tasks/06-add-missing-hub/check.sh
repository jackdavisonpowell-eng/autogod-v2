#!/bin/sh
set -eu
python3 - <<'PY'
import glob, sys
expect_unchanged = {"has-hub.md": open("has-hub.md").read() if False else None}
orig = {
    "has-hub.md": "# Has Hub\n\nSome content here.\n\nHub: [[Infrastructure Hub]]\n",
    "has-hub-2.md": "# Has Hub Two\n\nHub: [[Preferences Hub]]\n",
}
for fn, content in orig.items():
    got = open(fn).read()
    if got != content:
        print(f"FAIL: {fn} was modified but should not have been"); sys.exit(1)
for fn in ("no-hub-1.md", "no-hub-2.md"):
    got = open(fn).read()
    lines = [l for l in got.splitlines() if l.strip().startswith("Hub:")]
    if not lines:
        print(f"FAIL: {fn} still has no Hub: line"); sys.exit(1)
    if "[[Unsorted]]" not in lines[-1]:
        print(f"FAIL: {fn} Hub line wrong: {lines[-1]!r}"); sys.exit(1)
print("OK")
PY
