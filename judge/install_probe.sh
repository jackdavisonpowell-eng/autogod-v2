#!/usr/bin/env bash
# judge/install_probe.sh <name> [--dry-run]
#
# For an exec probe: writes ~/bin/<target>, a wrapper that appends
# "<ts> <target>" to state/usage.log and then execs the project's run.sh.
# http/link/file probes install themselves (the project's own code writes
# the access log / vault note / target file) — nothing for this script to do.
#
# Called by the model itself via Bash once milestone_at is set (see
# loop/CLAUDE.md step 4); guard.py lets the Bash call through (it isn't one
# of the denied command shapes) but would deny the model writing to ~/bin
# directly, which is the point — only this trusted script writes there.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${AUTOGOD_ROOT:-$(cd "$HERE/.." && pwd)}"
STATE="${AUTOGOD_STATE_DIR:-$ROOT/state}"

NAME="${1:-}"
if [ -z "$NAME" ]; then
    echo "usage: install_probe.sh <name> [--dry-run]" >&2
    exit 2
fi
DRY_RUN=0
if [ "${2:-}" = "--dry-run" ]; then
    DRY_RUN=1
fi

PROJECT_DIR="$STATE/current/$NAME"
JUDGE_YAML="$PROJECT_DIR/judge.yaml"
if [ ! -f "$JUDGE_YAML" ]; then
    echo "install_probe.sh: no judge.yaml at $JUDGE_YAML" >&2
    exit 1
fi

PY_OUT="$(python3 "$HERE/_read_probe.py" "$JUDGE_YAML")"
KIND="$(printf '%s' "$PY_OUT" | cut -f1)"
TARGET="$(printf '%s' "$PY_OUT" | cut -f2)"

if [ "$KIND" != "exec" ]; then
    echo "install_probe.sh: probe kind is '$KIND', no ~/bin wrapper needed" \
         "(http/link/file probes install themselves via the project's own code)."
    exit 0
fi

if [ -z "$TARGET" ]; then
    echo "install_probe.sh: probe.target is empty in $JUDGE_YAML" >&2
    exit 1
fi

WRAPPER="$HOME/bin/$TARGET"
RUN_SH="$PROJECT_DIR/run.sh"
USAGE_LOG="$STATE/usage.log"

if [ "$DRY_RUN" = "1" ]; then
    echo "would write $WRAPPER (execs $RUN_SH, logs to $USAGE_LOG)"
    exit 0
fi

mkdir -p "$HOME/bin"
cat > "$WRAPPER" <<WRAPEOF
#!/usr/bin/env bash
echo "\$(date -u +%Y-%m-%dT%H:%M:%SZ) $TARGET" >> "$USAGE_LOG"
exec "$RUN_SH" "\$@"
WRAPEOF
chmod +x "$WRAPPER"
echo "installed $WRAPPER"
