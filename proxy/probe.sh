#!/usr/bin/env bash
# probe.sh — run `claude -p` 20 times against the proxy, headless, and score.
# Run this ON thebeast (it invokes the local claude binary + reads proxy.log there).
# Writes proxy/probe-results.md next to this script.
set -uo pipefail

PROXY_LOG="${AUTOGOD_PROXY_LOG:-$HOME/autogod-v2/state/proxy.log}"
SCRATCH="/tmp/autogod-probe"
WORKDIR="$SCRATCH/work"   # ALL claude invocations run here: --resume needs the same cwd
                          # as the session it's resuming (sessions are keyed by project dir).
OUT="$(cd "$(dirname "$0")" && pwd)/probe-results.md"
N=20
COLD_RUNS="1 8 15"   # runs that start a fresh session; all others resume the most recent one

export ANTHROPIC_BASE_URL=http://127.0.0.1:11499
export ANTHROPIC_AUTH_TOKEN=local
export ANTHROPIC_DEFAULT_OPUS_MODEL=autogod
export ANTHROPIC_DEFAULT_SONNET_MODEL=autogod
export ANTHROPIC_DEFAULT_HAIKU_MODEL=autogod
export CLAUDE_CODE_ATTRIBUTION_HEADER=0
export CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1
export PATH="$HOME/.local/bin:$PATH"
CLAUDE_BIN="${CLAUDE_BIN:-$HOME/.local/bin/claude}"

mkdir -p "$SCRATCH" "$WORKDIR"
SESSION_ID=""
declare -a ROWS

is_cold() {
    local n="$1"
    for c in $COLD_RUNS; do [ "$c" = "$n" ] && return 0; done
    return 1
}

for i in $(seq -w 1 "$N"); do
    n=$((10#$i))
    RUNDIR="$SCRATCH/run-$i"     # logs only (out.json, err.log) -- claude itself runs in $WORKDIR
    rm -rf "$RUNDIR"; mkdir -p "$RUNDIR"
    FNAME="hello_${i}.txt"
    rm -f "$WORKDIR/$FNAME"
    TASK="Create a file ${FNAME} containing the word autogod, then read it back and reply DONE"
    T0=$(date +%s.%N)
    LOG_START=$(date +%Y-%m-%dT%H:%M:%S)  # local time: matches adapter-proxy.py's time.strftime()
    sleep 1  # ensure this run's proxy-log window doesn't collide with the prior run's tail

    if [ "$n" -eq 1 ] || is_cold "$n" || [ -z "$SESSION_ID" ]; then
        MODE="cold"
        RAW=$(cd "$WORKDIR" && timeout 180 "$CLAUDE_BIN" -p "$TASK" --output-format json \
            --allowedTools Read,Write,Edit,Bash,Grep,Glob --max-turns 6 2>"$RUNDIR/err.log")
        RC=$?
    else
        MODE="warm-resume"
        RAW=$(cd "$WORKDIR" && timeout 180 "$CLAUDE_BIN" -p "$TASK" --output-format json --resume "$SESSION_ID" \
            --allowedTools Read,Write,Edit,Bash,Grep,Glob --max-turns 6 2>"$RUNDIR/err.log")
        RC=$?
    fi
    T1=$(date +%s.%N)
    LOG_END=$(date +%Y-%m-%dT%H:%M:%S)  # local time: matches adapter-proxy.py's time.strftime()
    SECS=$(awk -v a="$T0" -v b="$T1" 'BEGIN{printf "%.1f", b-a}')
    echo "$RAW" > "$RUNDIR/out.json"

    SID=$(echo "$RAW" | python3 -c "import json,sys
try:
    d=json.load(sys.stdin); print(d.get('session_id') or '')
except Exception: print('')" 2>/dev/null)
    # track the most recent COLD session's id -- warm runs always resume off the latest cold one
    if [ -n "$SID" ] && [ "$MODE" = "cold" ]; then SESSION_ID="$SID"; fi

    TURNS=$(echo "$RAW" | python3 -c "import json,sys
try:
    d=json.load(sys.stdin); print(d.get('num_turns') or 0)
except Exception: print(0)" 2>/dev/null)
    IS_ERR=$(echo "$RAW" | python3 -c "import json,sys
try:
    d=json.load(sys.stdin); print(1 if d.get('is_error') else 0)
except Exception: print(1)" 2>/dev/null)

    if [ -f "$WORKDIR/$FNAME" ] && grep -q autogod "$WORKDIR/$FNAME" 2>/dev/null; then
        SUCCESS=1
    else
        SUCCESS=0
    fi

    # tokens + api-call count + proxy errors for this run: proxy-log entries in [start,end]
    TOKENS=$(python3 - "$PROXY_LOG" "$LOG_START" "$LOG_END" <<'PY'
import json, sys
path, start, end = sys.argv[1], sys.argv[2], sys.argv[3]
tin = tout = calls = errs = 0
try:
    for line in open(path):
        try: r = json.loads(line)
        except Exception: continue
        ts = r.get("ts", "")
        if start <= ts <= end:
            calls += 1
            if int(r.get("status") or 0) >= 400: errs += 1
            tin += r.get("input_tokens") or 0
            tout += r.get("output_tokens") or 0
except FileNotFoundError:
    pass
print(f"{tin} {tout} {calls} {errs}")
PY
)
    TOK_IN=$(echo "$TOKENS" | awk '{print $1}')
    TOK_OUT=$(echo "$TOKENS" | awk '{print $2}')
    API_CALLS=$(echo "$TOKENS" | awk '{print $3}')
    API_ERRS=$(echo "$TOKENS" | awk '{print $4}')

    ROWS+=("| $n | $MODE | $RC | $SECS | $SUCCESS | $TURNS | $API_CALLS | $API_ERRS | $IS_ERR | $TOK_IN | $TOK_OUT |")
    echo "run $n [$MODE] rc=$RC secs=$SECS success=$SUCCESS turns=$TURNS" >&2
done

GPU=$(nvidia-smi --query-gpu=index,name,utilization.gpu,memory.used --format=csv,noheader 2>/dev/null)

{
    echo "# AUTOGOD v2 proxy probe results"
    echo
    echo "Run: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo
    echo "Note: resume requires the same cwd as the original session (Claude Code keys"
    echo "sessions by project directory) -- all 20 runs execute in one shared workdir"
    echo "($WORKDIR), with per-run file names (hello_NN.txt) to keep them distinguishable."
    echo
    echo "GPU util during run:"
    echo '```'
    echo "$GPU"
    echo '```'
    echo
    echo "| run | mode | exit | secs | success | turns | api_calls | api_errs | is_error | tok_in | tok_out |"
    echo "|---|---|---|---|---|---|---|---|---|---|---|"
    for r in "${ROWS[@]}"; do echo "$r"; done
    echo
    SUCC_N=0
    for r in "${ROWS[@]}"; do
        s=$(echo "$r" | awk -F'|' '{print $6}' | tr -d ' ')
        [ "$s" = "1" ] && SUCC_N=$((SUCC_N+1))
    done
    ERR_N=0
    for r in "${ROWS[@]}"; do
        e=$(echo "$r" | awk -F'|' '{print $10}' | tr -d ' ')
        [ "$e" = "1" ] && ERR_N=$((ERR_N+1))
    done
    APIERR_N=0; APICALL_N=0
    for r in "${ROWS[@]}"; do
        ae=$(echo "$r" | awk -F'|' '{print $9}' | tr -d ' ')
        ac=$(echo "$r" | awk -F'|' '{print $8}' | tr -d ' ')
        APIERR_N=$((APIERR_N + ${ae:-0})); APICALL_N=$((APICALL_N + ${ac:-0}))
    done
    WARM_SECS=$(for r in "${ROWS[@]}"; do
        mode=$(echo "$r" | awk -F'|' '{print $3}' | tr -d ' ')
        [ "$mode" = "warm-resume" ] && echo "$r" | awk -F'|' '{print $5}' | tr -d ' '
    done | sort -n)
    WARM_MED=$(echo "$WARM_SECS" | awk '{a[NR]=$1} END{if(NR==0){print "n/a"}else{print a[int((NR+1)/2)]}}')
    COLD_SECS=$(for r in "${ROWS[@]}"; do
        mode=$(echo "$r" | awk -F'|' '{print $3}' | tr -d ' ')
        [ "$mode" = "cold" ] && echo "$r" | awk -F'|' '{print $5}' | tr -d ' '
    done | tr '\n' ' ')

    echo "## Summary"
    echo "- success: ${SUCC_N}/${N}  (gate: >=18/20)"
    echo "- claude-reported is_error rate: ${ERR_N}/${N}"
    echo "- proxy api-call error rate: ${APIERR_N}/${APICALL_N} requests (>=400 status)"
    echo "- median warm (--resume) turn secs: ${WARM_MED}"
    echo "- cold run secs: ${COLD_SECS}"
    echo "- GPU util during: see block above"
} > "$OUT"

echo "wrote $OUT" >&2
