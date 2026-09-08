#!/usr/bin/env bash
# bench/night.sh -- uncontended night harness bench for AUTOGOD v2. RUNS ON
# thebeast. Waits for the V100 night brain (:11467) to come up (FRIDAY's own
# night-lane.sh does that swap when Jack tells her he's going to bed -- see
# bench/NIGHT.md for the full mechanics). This script never calls systemctl
# and never touches night-lane.sh/friday-brain/friday-sight/autogod-night-brain
# -- it only polls :11467/health (read-only) and, once healthy, drives the
# bench runner: first claude-code via the night adapter proxy (:11498),
# then dsh pointed DIRECTLY at :11467 (dsh needs raw OpenAI-style system
# messages; the proxy's system-fold would break it -- see bench/dsh/NOTES.md).
#
# Deadline: FRIDAY takes the V100 back nominally at 08:00 local, hard
# backstop 08:05 (bench/NIGHT.md). The dsh half is skipped/aborted once the
# wall clock reaches 07:40 local (deadline minus 20 min), so it never runs
# into the hand-back window.
#
# Idempotent: a DONE-<date> marker short-circuits a second run for the same
# calendar day; a flock prevents two instances running at once. Killable:
# a trap restores ~/.dsh/settings.yaml no matter how this exits.
set -uo pipefail

ROOT="${AUTOGOD_ROOT:-$HOME/autogod-v2}"
cd "$ROOT" || { echo "cannot cd to $ROOT" >&2; exit 1; }

# `claude` and `dsh` both live under nvm's node 22 (thebeast's system node is
# too old for either) -- source it once, up front, so both halves find their
# binary on PATH. Harmless to source again inside the dsh half below.
[ -f "$ROOT/bench/dsh/env.sh" ] && source "$ROOT/bench/dsh/env.sh"

mkdir -p "$ROOT/state" "$ROOT/docs/bench"
LOG="$ROOT/state/bench-night.log"
log() { printf '%s night: %s\n' "$(date '+%F %T')" "$*" | tee -a "$LOG" >&2; }

DATE_TAG="$(date +%F)"
DAY_OUT="docs/bench/${DATE_TAG}-claude-code"
DSH_OUT="docs/bench/${DATE_TAG}-dsh"
COMBINED="docs/bench/${DATE_TAG}-TABLE.md"
DONE_FILE="docs/bench/DONE-${DATE_TAG}"
VAULT_BENCH_DIR="/data/vault/AUTOGOD/bench"

# --- idempotency: one run per calendar day, one instance at a time ---
if [ -f "$DONE_FILE" ]; then
    log "already done today ($DONE_FILE exists) -- exiting"
    exit 0
fi
LOCKFILE="$ROOT/state/bench-night.lock"
exec 9>"$LOCKFILE"
if ! flock -n 9; then
    log "another bench-night run holds the lock ($LOCKFILE) -- exiting"
    exit 0
fi

# --- dsh settings swap state + restore-on-any-exit trap ---
DSH_SETTINGS="$HOME/.dsh/settings.yaml"
DSH_SETTINGS_BAK="$HOME/.dsh/settings.yaml.bak-bench-night"
SETTINGS_SWAPPED=0

restore_settings() {
    if [ "$SETTINGS_SWAPPED" = 1 ] && [ -f "$DSH_SETTINGS_BAK" ]; then
        cp "$DSH_SETTINGS_BAK" "$DSH_SETTINGS"
        rm -f "$DSH_SETTINGS_BAK"
        SETTINGS_SWAPPED=0
        log "restored $DSH_SETTINGS from backup"
    fi
}
on_exit() { restore_settings; }
trap on_exit EXIT INT TERM

# --- deadline math: next 07:40 local (today's if we haven't hit it yet,
# else tomorrow's -- this script normally starts in the evening, so it's
# almost always tomorrow's) ---
DEADLINE_HHMM="07:40"
DEADLINE_EPOCH="$(date -d "$DEADLINE_HHMM" +%s)"
NOW_EPOCH_AT_START="$(date +%s)"
if [ "$DEADLINE_EPOCH" -le "$NOW_EPOCH_AT_START" ]; then
    DEADLINE_EPOCH="$(date -d "tomorrow $DEADLINE_HHMM" +%s)"
fi
log "dsh-half deadline: $(date -d "@$DEADLINE_EPOCH" '+%F %T') (FRIDAY-morning nominal 08:00 / hard backstop 08:05, minus 20min)"
past_deadline() { [ "$(date +%s)" -ge "$DEADLINE_EPOCH" ]; }

# Reuse bench/run.py's write_table() to synthesize a TABLE.md from whatever
# rows made it into results.jsonl, for a half that got cut short before its
# own normal end-of-loop write_table() call ran.
write_fallback_table() {
    local driver="$1" out_dir="$2"
    [ -f "$out_dir/TABLE.md" ] && return 0
    [ -f "$out_dir/results.jsonl" ] || return 0
    python3 - "$driver" "$out_dir" <<'PYEOF'
import importlib.util, json, os, sys
driver, out_dir = sys.argv[1], sys.argv[2]
spec = importlib.util.spec_from_file_location("bench_run", "bench/run.py")
run_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_mod)
rows = []
with open(os.path.join(out_dir, "results.jsonl")) as f:
    for line in f:
        line = line.strip()
        if line:
            rows.append(json.loads(line))
if rows:
    run_mod.write_table(rows, driver, out_dir)
    print(f"fallback TABLE.md written from {len(rows)} partial row(s) in {out_dir}")
PYEOF
}

# --- wait for the night brain (poll every 60s, give up after 14h) ---
WAIT_INTERVAL=60
WAIT_MAX_SECS=$((14 * 3600))
waited=0
log "waiting for night brain :11467/health (poll ${WAIT_INTERVAL}s, giving up after 14h)"
while true; do
    if curl -s --max-time 5 http://127.0.0.1:11467/health 2>/dev/null | grep -q '"ok"'; then
        log "night brain :11467 healthy after ${waited}s wait"
        break
    fi
    if [ "$waited" -ge "$WAIT_MAX_SECS" ]; then
        log "gave up waiting for :11467 after 14h -- nothing to bench tonight, exiting"
        exit 0
    fi
    sleep "$WAIT_INTERVAL"
    waited=$((waited + WAIT_INTERVAL))
done

if past_deadline; then
    log "already past the 07:40 deadline by the time :11467 came up -- skipping both halves"
    mkdir -p "$DAY_OUT" "$DSH_OUT"
    CC_RC="skipped(past-deadline)"
    DSH_RC="skipped(past-deadline)"
else
    # --- claude-code half, via the night adapter proxy (:11498 -> :11467) ---
    log "=== claude-code half start -> $DAY_OUT ==="
    ( set -a; source "$ROOT/loop/env.sh"; set +a
      export AUTOGOD_LANE=night
      export ANTHROPIC_BASE_URL=http://127.0.0.1:11498
      python3 bench/run.py --driver claude-code \
          --out "$DAY_OUT" \
          --proxy-log "$ROOT/state/proxy-night.log" \
          --budget-secs 900
    ) >>"$LOG" 2>&1
    CC_RC=$?
    log "=== claude-code half done rc=$CC_RC ==="
    write_fallback_table claude-code "$DAY_OUT"

    # --- dsh half, direct against :11467 (bypasses the proxy) ---
    if past_deadline; then
        log "past the 07:40 deadline after the claude-code half -- skipping dsh half entirely"
        mkdir -p "$DSH_OUT"
        DSH_RC="skipped(past-deadline)"
    else
        remaining=$(( DEADLINE_EPOCH - $(date +%s) ))
        if [ "$remaining" -le 60 ]; then
            log "under a minute left before the 07:40 deadline -- skipping dsh half"
            mkdir -p "$DSH_OUT"
            DSH_RC="skipped(past-deadline)"
        else
            log "swapping $DSH_SETTINGS -> :11467 (backup at $DSH_SETTINGS_BAK)"
            if [ -f "$DSH_SETTINGS" ]; then
                cp "$DSH_SETTINGS" "$DSH_SETTINGS_BAK"
                SETTINGS_SWAPPED=1
                sed -i 's#127\.0\.0\.1:11466#127.0.0.1:11467#g' "$DSH_SETTINGS"
                log "=== dsh half start -> $DSH_OUT (capped at ${remaining}s by the deadline) ==="
                ( source "$ROOT/bench/dsh/env.sh"
                  cap=$(( remaining < 900 ? remaining : 900 ))
                  timeout --kill-after=15 "${remaining}s" \
                      python3 bench/run.py --driver dsh \
                          --out "$DSH_OUT" \
                          --budget-secs "$cap"
                ) >>"$LOG" 2>&1
                DSH_RC=$?
                log "=== dsh half done rc=$DSH_RC ==="
                write_fallback_table dsh "$DSH_OUT"
                restore_settings
            else
                log "WARNING: $DSH_SETTINGS not found -- cannot run dsh half"
                mkdir -p "$DSH_OUT"
                DSH_RC="skipped(no-settings.yaml)"
            fi
        fi
    fi
fi

# --- combined table + delivery ---
{
    echo "# AUTOGOD v2 night bench -- ${DATE_TAG}"
    echo
    echo "Brain: Huihui-Qwen3.8-27B-abliterated Q4_K_M, night copy on port :11467 |" \
         "GPU: V100 (FRIDAY's card, borrowed overnight by night-lane.sh) |" \
         "FRIDAY-morning deadline: 08:00 nominal / 08:05 hard backstop" \
         "(bench/NIGHT.md); this bench's dsh half cuts off at 07:40."
    echo
    echo "claude-code exit: ${CC_RC}  |  dsh exit: ${DSH_RC}"
    echo
    echo "## claude-code driver (via night proxy :11498 -> :11467)"
    echo
    if [ -f "$DAY_OUT/TABLE.md" ]; then
        cat "$DAY_OUT/TABLE.md"
    else
        echo "(no TABLE.md -- see $LOG)"
    fi
    echo
    echo "## dsh driver (direct :11467)"
    echo
    if [ -f "$DSH_OUT/TABLE.md" ]; then
        cat "$DSH_OUT/TABLE.md"
    else
        echo "(no TABLE.md -- ${DSH_RC:-not run}, see $LOG)"
    fi
} >"$COMBINED"
log "wrote $COMBINED"

mkdir -p "$VAULT_BENCH_DIR" 2>/dev/null && cp "$COMBINED" "$VAULT_BENCH_DIR/" \
    && log "copied to $VAULT_BENCH_DIR/$(basename "$COMBINED")" \
    || log "WARNING: could not copy to $VAULT_BENCH_DIR (not present/writable?)"

touch "$DONE_FILE"
log "touched $DONE_FILE -- night bench run complete"
