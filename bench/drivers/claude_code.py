#!/usr/bin/env python3
"""claude-code driver for bench/run.py.

Invokes the headless Claude Code CLI:

    claude -p "<prompt>" --output-format json \
        --allowedTools Read,Write,Edit,Bash,Grep,Glob [--max-turns N]

in `cwd`, with `env` passed through untouched (so the caller decides which
ANTHROPIC_BASE_URL / proxy / model the CLI talks to -- this driver has no
opinion about that).

`--max-turns` is only appended if the installed CLI still supports it (some
versions dropped it in favour of --max-budget-usd); its absence is not an
error, since bench/run.py already enforces a hard wall-clock budget_secs
kill regardless.

The sanctioned output is `--output-format json`'s single result object:
we read num_turns, is_error and result from it, per the build spec. As a
best-effort *enhancement* (not required, never fatal if it fails) we also
try to locate the on-disk session transcript
(~/.claude/projects/*/<session_id>.jsonl) to count real tool_use blocks
(tool_calls) and tool_result blocks flagged is_error (tool_errors); the
transcript format is internal to Claude Code and may not match at any
given version, so this is wrapped in try/except and simply left as None
if anything doesn't line up.
"""
import glob
import json
import os
import signal
import subprocess
import time

_HELP_CACHE = {}


def _cli_supports_max_turns():
    if "ok" not in _HELP_CACHE:
        try:
            r = subprocess.run(
                ["claude", "-p", "--help"],
                capture_output=True, text=True, timeout=20,
            )
            _HELP_CACHE["ok"] = "--max-turns" in (r.stdout + r.stderr)
        except Exception:
            _HELP_CACHE["ok"] = False
    return _HELP_CACHE["ok"]


def _find_transcript(session_id):
    if not session_id:
        return None
    hits = glob.glob(os.path.expanduser(f"~/.claude/projects/*/{session_id}.jsonl"))
    return hits[0] if hits else None


def _count_tool_stats(transcript_path):
    tool_calls = 0
    tool_errors = 0
    with open(transcript_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            msg = rec.get("message")
            if not isinstance(msg, dict):
                continue
            content = msg.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type")
                if btype == "tool_use":
                    tool_calls += 1
                elif btype == "tool_result" and block.get("is_error"):
                    tool_errors += 1
    return tool_calls, tool_errors


def run(prompt, cwd, budget_secs, max_turns, env):
    """Run one bench task through `claude -p`.

    Returns dict(exit_code, turns, tool_calls, tool_errors, raw_log_path,
    is_error, result, session_id, tokens_in, tokens_out).
    """
    os.makedirs(cwd, exist_ok=True)
    raw_log_path = os.path.join(cwd, ".claude_code_driver.log")

    cmd = [
        "claude", "-p", prompt,
        "--output-format", "json",
        "--allowedTools", "Read,Write,Edit,Bash,Grep,Glob",
    ]
    if max_turns and _cli_supports_max_turns():
        cmd += ["--max-turns", str(max_turns)]

    out = {
        "exit_code": None, "turns": None, "tool_calls": None,
        "tool_errors": None, "raw_log_path": raw_log_path,
        "is_error": None, "result": None, "session_id": None,
        "tokens_in": None, "tokens_out": None,
    }

    t0 = time.time()
    proc = subprocess.Popen(
        cmd, cwd=cwd, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, start_new_session=True,
    )
    try:
        stdout, _ = proc.communicate(timeout=budget_secs)
        out["exit_code"] = proc.returncode
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            time.sleep(2)
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass
        stdout, _ = proc.communicate()
        out["exit_code"] = 124  # timeout convention

    with open(raw_log_path, "w") as f:
        f.write(stdout or "")

    try:
        d = json.loads((stdout or "").strip().splitlines()[-1]) if stdout and stdout.strip() else {}
    except Exception:
        d = {}

    out["turns"] = d.get("num_turns")
    out["is_error"] = d.get("is_error")
    out["result"] = d.get("result")
    out["session_id"] = d.get("session_id")
    usage = d.get("usage") or {}
    out["tokens_in"] = usage.get("input_tokens")
    out["tokens_out"] = usage.get("output_tokens")

    denials = d.get("permission_denials")
    if isinstance(denials, list) and out["tool_errors"] is None:
        out["tool_errors"] = len(denials)

    try:
        tp = _find_transcript(out["session_id"])
        if tp:
            tc, te = _count_tool_stats(tp)
            out["tool_calls"] = tc
            # prefer real transcript error count over permission_denials guess
            out["tool_errors"] = te
    except Exception:
        pass

    out["wall_secs"] = round(time.time() - t0, 1)
    return out


if __name__ == "__main__":
    import sys
    r = run(
        prompt=sys.argv[1] if len(sys.argv) > 1 else "reply with the word pong",
        cwd=os.getcwd(), budget_secs=120, max_turns=5, env=os.environ.copy(),
    )
    print(json.dumps(r, indent=2))
