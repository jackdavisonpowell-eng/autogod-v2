#!/usr/bin/env bash
# Rsync proxy/ to thebeast, install + enable the systemd user unit.
# Falls back to a nohup start if user lingering is off (systemctl --user
# won't run outside a login session in that case).
set -euo pipefail
HOST="${AUTOGOD_HOST:-thebeast}"
REMOTE_DIR="autogod-v2/proxy"

echo "== rsync proxy/ -> ${HOST}:~/${REMOTE_DIR}/"
rsync -az --exclude '__pycache__' "$(dirname "$0")/" "${HOST}:~/${REMOTE_DIR}/"

ssh "$HOST" bash -s <<'REMOTE'
set -euo pipefail
mkdir -p ~/.config/systemd/user ~/autogod-v2/state
cp ~/autogod-v2/proxy/autogod-v2-proxy.service ~/.config/systemd/user/autogod-v2-proxy.service
cp ~/autogod-v2/proxy/autogod-v2-proxy-night.service ~/.config/systemd/user/autogod-v2-proxy-night.service

LINGER=$(loginctl show-user "$(whoami)" 2>/dev/null | grep -oP 'Linger=\K.*' || echo "unknown")
echo "linger=${LINGER}"

if systemctl --user daemon-reload 2>/dev/null; then
    OK_DAY=0; OK_NIGHT=0
    systemctl --user enable --now autogod-v2-proxy.service 2>/dev/null && OK_DAY=1
    systemctl --user enable --now autogod-v2-proxy-night.service 2>/dev/null && OK_NIGHT=1
    if [ "$OK_DAY" = 1 ] && [ "$OK_NIGHT" = 1 ]; then
        echo "MODE=systemd-user"
        sleep 1
        systemctl --user status autogod-v2-proxy.service --no-pager -l | head -10
        systemctl --user status autogod-v2-proxy-night.service --no-pager -l | head -10
        exit 0
    fi
fi

echo "MODE=nohup-fallback (systemctl --user unavailable, linger=${LINGER})"
pkill -f 'autogod-v2/proxy/adapter-proxy.py' 2>/dev/null || true
sleep 0.3
AUTOGOD_UPSTREAM=http://127.0.0.1:11466 AUTOGOD_PROXY_PORT=11499 \
    AUTOGOD_PROXY_LOG=~/autogod-v2/state/proxy.log \
    nohup python3 ~/autogod-v2/proxy/adapter-proxy.py \
    >> ~/autogod-v2/state/proxy.nohup.log 2>&1 &
disown
AUTOGOD_UPSTREAM=http://127.0.0.1:11467 AUTOGOD_PROXY_PORT=11498 \
    AUTOGOD_PROXY_LOG=~/autogod-v2/state/proxy-night.log \
    nohup python3 ~/autogod-v2/proxy/adapter-proxy.py \
    >> ~/autogod-v2/state/proxy-night.nohup.log 2>&1 &
disown
sleep 1
pgrep -fa 'autogod-v2/proxy/adapter-proxy.py' || { echo "FAILED to start via nohup"; exit 1; }
REMOTE

echo "== verify"
sleep 1
ssh "$HOST" "curl -s -o /dev/null -w 'proxy day (:11499) http status: %{http_code}\n' -X POST http://127.0.0.1:11499/v1/messages -H 'content-type: application/json' -d '{}' || true"
ssh "$HOST" "curl -s -o /dev/null -w 'proxy night (:11498) http status: %{http_code}\n' -X POST http://127.0.0.1:11498/v1/messages -H 'content-type: application/json' -d '{}' || true"
