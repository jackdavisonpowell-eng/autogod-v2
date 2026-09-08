#!/bin/sh
set -eu
chmod +x run.sh 2>/dev/null || true
PORT=$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')
./run.sh "$PORT" >server.out 2>&1 &
SRVPID=$!
cleanup() { kill "$SRVPID" 2>/dev/null || true; wait "$SRVPID" 2>/dev/null || true; }
trap cleanup EXIT
OK=0
for i in $(seq 1 50); do
    if python3 -c "
import urllib.request, sys
try:
    r = urllib.request.urlopen('http://127.0.0.1:$PORT/health', timeout=1)
    sys.exit(0 if r.status == 200 else 1)
except Exception:
    sys.exit(1)
"; then OK=1; break; fi
    sleep 0.2
done
[ "$OK" = "1" ] || { echo "FAIL: server never became healthy"; cat server.out; exit 1; }
python3 - "$PORT" <<'PY'
import urllib.request, json, sys
port = sys.argv[1]
r = urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2)
body = json.loads(r.read())
if body.get("status") != "ok":
    print(f"FAIL: /health body wrong: {body}"); sys.exit(1)
r2 = urllib.request.urlopen(f"http://127.0.0.1:{port}/index.html", timeout=2)
data = r2.read()
expected = open("site/index.html", "rb").read()
if data != expected:
    print(f"FAIL: /index.html content mismatch"); sys.exit(1)
r3 = urllib.request.urlopen(f"http://127.0.0.1:{port}/about.txt", timeout=2)
data3 = r3.read()
expected3 = open("site/about.txt", "rb").read()
if data3 != expected3:
    print(f"FAIL: /about.txt content mismatch"); sys.exit(1)
print("OK")
PY
