#!/usr/bin/env bash
# loop/run.sh — one pass: look -> (pick or build) -> judge.
# See docs/ARCHITECTURE.md ("One pass"). Safe to re-run; never aborts the
# pass on a phase failure (a bad night must not wedge the systemd timer).
#
# AUTOGOD_MODE=lookpick (build-order step 2: "LOOK + gate, no build, for a
# week, candidate lists in the vault so Jack can circle one"): look -> pick
# --dry-run only. No build, no judge. The dry-run verdict lands on today's
# candidates file, which is then copied to $VAULT/AUTOGOD/candidates/.
# AUTOGOD_MODE unset or "full" (default): the normal look -> pick-or-build ->
# judge pass.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${AUTOGOD_ROOT:-$(cd "$HERE/.." && pwd)}"
STATE="${AUTOGOD_STATE_DIR:-$ROOT/state}"
LANE="${AUTOGOD_LANE:-day}"
MODE="${AUTOGOD_MODE:-full}"
PY="${AUTOGOD_PYTHON:-python3}"

if [ "$LANE" = "night" ]; then
    DEFAULT_BUDGET=10800
else
    DEFAULT_BUDGET=3600
fi
BUDGET_SECS="${AUTOGOD_BUDGET_SECS:-$DEFAULT_BUDGET}"

if [ -z "${VAULT:-}" ]; then
    echo "run.sh: VAULT must be set" >&2
    exit 1
fi

mkdir -p "$STATE" "$STATE/current" "$STATE/candidates" "$STATE/kept"
touch "$STATE/dead.md" "$STATE/passes.log"

export AUTOGOD_ROOT="$ROOT"
export AUTOGOD_STATE_DIR="$STATE"
export AUTOGOD_LANE="$LANE"
export AUTOGOD_DRIVER="${AUTOGOD_DRIVER:-claude_code}"
export VAULT

now_s() { date +%s; }
ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }

current_project_dir() {
    find "$STATE/current" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | sort | head -n1
}

t_pass_start=$(now_s)
overall_exit=0

# LOOK -----------------------------------------------------------------
AUTOGOD_PHASE=look "$PY" "$HERE/look.py" --vault "$VAULT" --state "$STATE"
look_exit=$?
[ "$look_exit" -ne 0 ] && overall_exit=$look_exit

if [ "$MODE" = "lookpick" ]; then
    # LOOK + gate only: pick --dry-run, then publish today's candidates
    # (with the appended Gate verdict) to the vault. No build, no judge.
    today="$(date +%Y-%m-%d)"
    AUTOGOD_PHASE=pick "$PY" "$HERE/pick.py" --state "$STATE" --root "$ROOT" --dry-run
    phase_exit=$?
    [ "$phase_exit" -ne 0 ] && overall_exit=$phase_exit

    cand_src="$STATE/candidates/$today.md"
    vault_dir="$VAULT/AUTOGOD/candidates"
    mkdir -p "$vault_dir"
    if [ -f "$cand_src" ]; then
        cp "$cand_src" "$vault_dir/$today.md"
    fi

    t_pass_end=$(now_s)
    seconds=$((t_pass_end - t_pass_start))
    printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$(ts)" "$LANE" "lookpick" "-" "$seconds" "$overall_exit" \
        >> "$STATE/passes.log"
    exit 0
fi

# PICK or BUILD ----------------------------------------------------------
proj_dir="$(current_project_dir)"
if [ -z "$proj_dir" ]; then
    phase="pick"
    AUTOGOD_PHASE=pick "$PY" "$HERE/pick.py" --state "$STATE" --root "$ROOT"
    phase_exit=$?
    proj_dir="$(current_project_dir)"
    proj_name="none"
    [ -n "$proj_dir" ] && proj_name="$(basename "$proj_dir")"
else
    phase="build"
    proj_name="$(basename "$proj_dir")"
    prompt="Read PROJECT.md. Do exactly the \`next:\` step. Before stopping, update next:, append to log:, keep run.sh working."
    AUTOGOD_PHASE=build "$PY" "$HERE/build.py" \
        --project-dir "$proj_dir" --budget-secs "$BUDGET_SECS" --prompt "$prompt"
    phase_exit=$?
fi
[ "$phase_exit" -ne 0 ] && overall_exit=$phase_exit

# JUDGE --------------------------------------------------------------------
AUTOGOD_PHASE=judge "$PY" "$ROOT/judge/judge.py" --state "$STATE"
judge_exit=$?
[ "$judge_exit" -ne 0 ] && overall_exit=$judge_exit

t_pass_end=$(now_s)
seconds=$((t_pass_end - t_pass_start))

printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$(ts)" "$LANE" "$phase" "$proj_name" "$seconds" "$overall_exit" \
    >> "$STATE/passes.log"

# A single pass never fails the timer: the run happened, it's logged, and
# any real trouble is visible in passes.log / guard.log / pick.log.
exit 0
