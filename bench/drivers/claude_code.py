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

Upstream preflight (bugfix, 2026-09-08): found while dry-running against the
night proxy (:11498) with the V100 night brain (:11467) deliberately down.
The proxy itself answers instantly with a clean 502 per request (confirmed
in state/proxy-night.log), but the Claude Code CLI's own HTTP client retries
5xx responses with backoff regardless -- so the *process* doesn't exit until
bench/run.py's hard budget_secs kill, even though the real answer ("upstream
is down") was known in under a second. That's not "fail fast and cleanly",
it's "fail slow and get killed". Before spawning the CLI we now do one quick
direct probe of ANTHROPIC_BASE_URL ourselves (a few-second timeout, no
retries) so an unreachable/5xx upstream is reported immediately without
waiting out the CLI's retry loop or the task's full budget. Skipped entirely
if ANTHROPIC_BASE_URL isn't set (real api.anthropic.com is not preflighted).
"""
import glob
import json
import os
import signal
import subprocess
import time
import urllib.error
import urllib.request

_HELP_CACHE = {}
PREFLIGHT_TIMEOUT_SECS = 5


def _preflight_upstream(env, timeout=PREFLIGHT_TIMEOUT_SECS):
    """Return (ok, detail). ok=True means either there's nothing to check
    (no ANTHROPIC_BASE_URL override) or the endpoint proved it has a live
    upstream behind it within `timeout` seconds.

    We deliberately POST an empty '{}' body, so ANY real HTTP response --
    even a 4xx/5xx application-level error like "'messages' is required"
    -- proves the upstream is alive and answering (confirmed live 2026-09-08
    against the day brain on :11466/:11499: a real, busy upstream answers
    the malformed preflight with its own 500, not a transport failure).
    bench/proxy/adapter-proxy.py's own convention is what makes this safe
    to interpret: it returns exactly HTTP 502 with an EMPTY body only when
    it itself failed to reach the upstream at the transport level (caught
    as a bare `except Exception`, before the `except HTTPError` clause that
    handles and forwards a real upstream response/status verbatim); any
    other status code -- including other 5xx -- means a real server
    answered. A bare connection failure straight to a non-proxied
    ANTHROPIC_BASE_URL (no proxy in front at all) surfaces the same way,
    as a generic exception with no HTTP status."""
    base = (env or {}).get("ANTHROPIC_BASE_URL")
    if not base:
        return True, "no ANTHROPIC_BASE_URL override, skipping preflight"
    url = base.rstrip("/") + "/v1/messages"
    req = urllib.request.Request(
        url, data=b"{}", method="POST",
        headers={"content-type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return True, f"preflight {url} -> HTTP {r.status}"
    except urllib.error.HTTPError as e:
        if e.code == 502:
            return False, f"preflight {url} -> HTTP 502 (proxy could not reach upstream)"
        return True, f"preflight {url} -> HTTP {e.code} (upstream is alive and answered)"
    except Exception as e:
        return False, f"preflight {url} -> {type(e).__name__}: {e} (no response at all)"


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

    ok, detail = _preflight_upstream(env)
    if not ok:
        with open(raw_log_path, "w") as f:
            f.write(f"preflight failed, claude was never started: {detail}\n")
        out["exit_code"] = 503
        out["is_error"] = True
        out["result"] = f"preflight failed: {detail}"
        out["wall_secs"] = round(time.time() - t0, 1)
        return out

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
