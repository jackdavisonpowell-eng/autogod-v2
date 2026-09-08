#!/bin/sh
set -eu
chmod +x run.sh 2>/dev/null || true
[ -f run.sh ] || { echo "FAIL: run.sh missing"; exit 1; }
./run.sh
[ -f output.html ] || { echo "FAIL: output.html missing"; exit 1; }
python3 - <<'PY'
import sys
html = open("output.html").read()
required = [
    "<h1>Title</h1>",
    "<h2>Section</h2>",
    "<strong>bold word</strong>",
    "<li>item one</li>",
    "<li>item two</li>",
    "<li>item three</li>",
]
for r in required:
    if r not in html:
        print(f"FAIL: missing {r!r}"); sys.exit(1)
if html.count("<li>") != 3:
    print(f"FAIL: expected exactly 3 <li>, got {html.count('<li>')}"); sys.exit(1)
print("OK")
PY
