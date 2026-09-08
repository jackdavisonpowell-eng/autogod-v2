#!/bin/sh
set -eu
[ -f Makefile ] || { echo "FAIL: Makefile missing"; exit 1; }
chmod +x run.sh 2>/dev/null || true
[ -f run.sh ] || { echo "FAIL: run.sh missing"; exit 1; }
if ! ./run.sh; then
    echo "FAIL: run.sh (make test) failed on a correct solution"; exit 1
fi
# Anti-cheat: mutate calc.py so the test SHOULD fail, verify make test then fails.
TMP=$(mktemp -d)
cp -r . "$TMP"/copy
( cd "$TMP"/copy && sed -i 's/return a + b/return a - b/' calc.py )
if ( cd "$TMP"/copy && make test ) >/dev/null 2>&1; then
    echo "FAIL: make test still passes after breaking calc.py (checker not real)"; rm -rf "$TMP"; exit 1
fi
rm -rf "$TMP"
echo "OK"
