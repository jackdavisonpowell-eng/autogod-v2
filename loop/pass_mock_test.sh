#!/usr/bin/env bash
# loop/pass_mock_test.sh — `make pass-mock`'s harness. Runs the real loop
# (look.py, pick.py, build.py, judge.py) with the mock driver, against the
# fixture vault at loop/drivers/mock_fixtures/vault/, in a throwaway state
# dir so it never touches the real state/ (state/dead.md is tracked).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
VAULT_FIXTURE="$HERE/drivers/mock_fixtures/vault"

TMP_STATE="$(mktemp -d)"
cleanup() { rm -rf "$TMP_STATE"; }
trap cleanup EXIT

export AUTOGOD_ROOT="$ROOT"
export AUTOGOD_STATE_DIR="$TMP_STATE"
export VAULT="$VAULT_FIXTURE"
export AUTOGOD_DRIVER="mock"
export AUTOGOD_LANE="day"
export AUTOGOD_BUDGET_SECS="5"

echo "pass-mock: pass 1 (expect pick)"
"$HERE/run.sh"

proj="$(find "$TMP_STATE/current" -mindepth 1 -maxdepth 1 -type d | head -n1)"
if [ -z "$proj" ]; then
    echo "pass-mock: FAIL — no project directory created on pass 1" >&2
    tail -n5 "$TMP_STATE/passes.log" 2>/dev/null >&2 || true
    exit 1
fi
name="$(basename "$proj")"
echo "pass-mock: pass 1 created state/current/$name"

for required in PROJECT.md PLAN.md judge.yaml .claude/settings.json CLAUDE.md; do
    if [ ! -e "$proj/$required" ]; then
        echo "pass-mock: FAIL — $proj/$required missing" >&2
        exit 1
    fi
done
if [ ! -L "$proj/CLAUDE.md" ]; then
    echo "pass-mock: FAIL — $proj/CLAUDE.md is not a symlink" >&2
    exit 1
fi

echo "pass-mock: pass 2 (expect build)"
"$HERE/run.sh"
last_line="$(tail -n1 "$TMP_STATE/passes.log")"
last_phase="$(printf '%s' "$last_line" | cut -f3)"
if [ "$last_phase" != "build" ]; then
    echo "pass-mock: FAIL — pass 2 phase was '$last_phase', expected 'build' ($last_line)" >&2
    exit 1
fi
echo "pass-mock: pass 2 hit build ($last_line)"

# Simulate the milestone having been reached 8 days before "today", with
# exactly 3 usage.log hits for the exec probe's target inside its 7-day
# judging window (loop/drivers/mock_fixtures/pick_response.txt promises
# probe.target=tire-check, keep_if=">=3 runs in 7 days").
python3 - "$proj" <<'PYEOF'
import sys
path = sys.argv[1] + "/PROJECT.md"
with open(path) as f:
    content = f.read()
content = content.replace("milestone_at:\n", "milestone_at: 2026-08-25\n", 1)
with open(path, "w") as f:
    f.write(content)
PYEOF

{
    echo "2026-08-26T08:00:00 tire-check"
    echo "2026-08-27T08:00:00 tire-check"
    echo "2026-08-28T08:00:00 tire-check"
} >> "$TMP_STATE/usage.log"

echo "pass-mock: judge --dry-run at milestone + 8 days"
verdict="$(AUTOGOD_TODAY=2026-09-02 python3 "$ROOT/judge/judge.py" --state "$TMP_STATE" --dry-run)"
echo "$verdict"
if ! printf '%s' "$verdict" | grep -q "'status': 'keep'"; then
    echo "pass-mock: FAIL — expected a keep verdict" >&2
    exit 1
fi
if [ ! -d "$proj" ]; then
    echo "pass-mock: FAIL — dry-run must not move/delete the project dir" >&2
    exit 1
fi

echo "pass-mock: lookpick mode (look + gate, no build)"
LP_STATE="$(mktemp -d)"
LP_VAULT="$(mktemp -d)"
cp -r "$VAULT_FIXTURE"/. "$LP_VAULT/"
lp_cleanup() { rm -rf "$LP_STATE" "$LP_VAULT"; }
trap 'lp_cleanup; cleanup' EXIT

AUTOGOD_MODE=lookpick AUTOGOD_ROOT="$ROOT" AUTOGOD_STATE_DIR="$LP_STATE" \
    VAULT="$LP_VAULT" AUTOGOD_DRIVER=mock AUTOGOD_LANE=day "$HERE/run.sh"

if [ -d "$LP_STATE/current" ] && [ -n "$(find "$LP_STATE/current" -mindepth 1 -maxdepth 1 -type d)" ]; then
    echo "pass-mock: FAIL — lookpick mode must never create state/current" >&2
    exit 1
fi
lp_last="$(tail -n1 "$LP_STATE/passes.log")"
if [ "$(printf '%s' "$lp_last" | cut -f3)" != "lookpick" ]; then
    echo "pass-mock: FAIL — lookpick pass logged as '$lp_last', expected phase 'lookpick'" >&2
    exit 1
fi
lp_today="$(date +%Y-%m-%d)"
lp_vault_file="$LP_VAULT/AUTOGOD/candidates/$lp_today.md"
if [ ! -f "$lp_vault_file" ]; then
    echo "pass-mock: FAIL — candidates file was not copied to \$VAULT/AUTOGOD/candidates/" >&2
    exit 1
fi
if ! grep -q "## Gate verdict" "$lp_vault_file"; then
    echo "pass-mock: FAIL — vault candidates copy has no Gate verdict section" >&2
    exit 1
fi
if ! grep -q "would have picked:" "$lp_vault_file"; then
    echo "pass-mock: FAIL — vault candidates copy has no 'would have picked:' line" >&2
    exit 1
fi
echo "pass-mock: lookpick mode published $lp_vault_file with a Gate verdict, no project created"

echo "pass-mock: OK"
