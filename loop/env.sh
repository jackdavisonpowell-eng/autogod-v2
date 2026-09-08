#!/usr/bin/env bash
# loop/env.sh — environment for every `claude` invocation the loop makes.
# Sourced by loop/drivers/claude_code.py (via `bash -c 'source env.sh; env -0'`),
# never executed directly. Values already exported by the caller win (the
# ${VAR:-default} pattern), so tests can override VAULT / AUTOGOD_ROOT /
# AUTOGOD_LANE before sourcing this.

export AUTOGOD_LANE="${AUTOGOD_LANE:-day}"

# Harness talks to a local adapter proxy in front of the brain. Day lane
# (P100 pair) sits on :11499; night lane (V100 copy) on :11498.
if [ "$AUTOGOD_LANE" = "night" ]; then
    export ANTHROPIC_BASE_URL="${ANTHROPIC_BASE_URL:-http://127.0.0.1:11498}"
else
    export ANTHROPIC_BASE_URL="${ANTHROPIC_BASE_URL:-http://127.0.0.1:11499}"
fi

export ANTHROPIC_AUTH_TOKEN="${ANTHROPIC_AUTH_TOKEN:-local}"
export ANTHROPIC_DEFAULT_OPUS_MODEL="${ANTHROPIC_DEFAULT_OPUS_MODEL:-autogod}"
export ANTHROPIC_DEFAULT_SONNET_MODEL="${ANTHROPIC_DEFAULT_SONNET_MODEL:-autogod}"
export ANTHROPIC_DEFAULT_HAIKU_MODEL="${ANTHROPIC_DEFAULT_HAIKU_MODEL:-autogod}"
export CLAUDE_CODE_ATTRIBUTION_HEADER="${CLAUDE_CODE_ATTRIBUTION_HEADER:-0}"
export CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="${CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC:-1}"

export VAULT="${VAULT:-/data/vault}"
export AUTOGOD_ROOT="${AUTOGOD_ROOT:-$HOME/autogod-v2}"

# Claude Code CLI: the nvm-installed copy (2.1.265, npm under ~/.nvm, no root) is the one
# the bench and the loop both use; ~/.local/bin/claude (2.1.220) is the older probe-only copy.
_nvm_bin="$(ls -d "$HOME"/.nvm/versions/node/v22*/bin 2>/dev/null | tail -1)"
[ -n "$_nvm_bin" ] && export PATH="$_nvm_bin:$PATH"
