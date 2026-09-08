#!/usr/bin/env python3
"""dsh (DeepSeek Harness) driver for bench/run.py.

Another agent owns bench/dsh/ (its env.sh, settings.yaml, NOTES.md wire
`dsh` to the local llama.cpp brain on thebeast, `@deepseek-ai/dsh@0.1.2-rc.1`
under nvm node 22). This file only *reads* bench/dsh/NOTES.md -- it is
never written there.

Per bench/dsh/NOTES.md (2026-09-08 install/smoke notes), the confirmed
headless invocation is:

    dsh --profile headless "<task text>"

run from the desired working directory (there is no --cwd flag; the
sandbox root is whatever `process.cwd()` is when dsh starts, so this
driver relies on subprocess `cwd=` alone, same as the claude-code driver).
`env` is passed through untouched -- the caller is responsible for
DSH_LOCAL_API_KEY, a Node >=22 `dsh` on PATH, etc (this driver does not
source env.sh itself).

Confirmed from NOTES.md, with real implications for what this driver can
report:

- Exit code 0 = task completed with a final turn; 1 = aborted/errored/no
  final turn. No other machine-readable status exists.
- stdout carries ONLY the final assistant message (plain text, no JSON
  mode exists for the headless profile).
- stderr carries reasoning deltas under `dsh: reasoning:`-style headers,
  one block per reasoning step -- the only proxy for "turns" available at
  all. This is a heuristic, not a real turn count.
- There is NO observable signal for individual tool calls or tool errors
  in headless output (no allowlist flag, no JSON, no transcript file
  documented) -- `tool_calls`/`tool_errors` are left as None rather than
  guessed. If a later dsh version adds structured output, wire it in here
  the way claude_code.py parses --output-format json.
- No --max-turns equivalent exists; `max_turns` is accepted for interface
  compatibility with the claude-code driver but is not passed to `dsh` --
  the wall-clock `budget_secs` kill in bench/run.py is the only turn/step
  cap available.
"""
import os
import re
import signal
import subprocess
import time

NOTES_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dsh", "NOTES.md")

# Each reasoning delta dsh prints to stderr is the closest thing to a
# per-turn marker in headless output (see NOTES.md); count them as a
# turns heuristic. Matches lines like "dsh: reasoning: ..." (colon-headed,
# case-insensitive prefix "dsh").
_REASONING_RE = re.compile(r'^\s*dsh:\s*reasoning', re.M | re.I)


def _read_notes():
    if os.path.exists(NOTES_PATH):
        try:
            return open(NOTES_PATH).read()
        except Exception:
            return None
    return None


def run(prompt, cwd, budget_secs, max_turns, env):
    """Run one bench task through `dsh --profile headless`.

    Returns dict(exit_code, turns, tool_calls, tool_errors, raw_log_path,
    result, wall_secs). tool_calls/tool_errors are always None -- see
    module docstring, headless dsh exposes no signal for them.
    """
    os.makedirs(cwd, exist_ok=True)
    raw_log_path = os.path.join(cwd, ".dsh_driver.log")
    _read_notes()  # informational; NOTES.md's confirmed invocation is hardcoded below

    cmd = ["dsh", "--profile", "headless", prompt]

    out = {
        "exit_code": None, "turns": None, "tool_calls": None,
        "tool_errors": None, "raw_log_path": raw_log_path, "result": None,
    }

    t0 = time.time()
    try:
        proc = subprocess.Popen(
            cmd, cwd=cwd, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, start_new_session=True,
        )
    except FileNotFoundError as e:
        with open(raw_log_path, "w") as f:
            f.write(f"dsh not found on PATH: {e}\n")
        out["exit_code"] = 127
        out["wall_secs"] = round(time.time() - t0, 1)
        return out

    try:
        stdout, stderr = proc.communicate(timeout=budget_secs)
        out["exit_code"] = proc.returncode
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            time.sleep(2)
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass
        stdout, stderr = proc.communicate()
        out["exit_code"] = 124  # timeout convention

    stdout = stdout or ""
    stderr = stderr or ""
    with open(raw_log_path, "w") as f:
        f.write("=== stdout ===\n" + stdout + "\n=== stderr ===\n" + stderr)

    out["result"] = stdout.strip()
    out["turns"] = len(_REASONING_RE.findall(stderr)) or None

    out["wall_secs"] = round(time.time() - t0, 1)
    return out


if __name__ == "__main__":
    import sys, json
    r = run(
        prompt=sys.argv[1] if len(sys.argv) > 1 else "reply with the word pong",
        cwd=os.getcwd(), budget_secs=120, max_turns=5, env=os.environ.copy(),
    )
    print(json.dumps(r, indent=2))
