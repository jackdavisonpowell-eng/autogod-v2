"""loop/drivers/claude_code.py — the real driver: headless `claude -p`.

Interface (shared with loop/drivers/mock.py):
    pick(prompt) -> str
    build(project_dir, prompt, budget_secs, resume_session_id=None) -> dict(
        session_id, exit_code, num_turns, is_error, seconds)
"""
import json
import os
import subprocess
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ENV_SH = os.path.join(_HERE, "..", "env.sh")

CLAUDE_BIN = os.environ.get("AUTOGOD_CLAUDE_BIN", "claude")
BUILD_TOOLS = "Read,Write,Edit,Bash,Grep,Glob,WebSearch"
PICK_TIMEOUT_SECS = int(os.environ.get("AUTOGOD_PICK_TIMEOUT_SECS", "300"))

# Cache: not every installed `claude` build has --max-turns (some only take
# --max-budget-usd). Probe once with --help and only pass the flag if it's
# there; the wall-clock budget kill (below) is the real backstop either way.
_MAX_TURNS_SUPPORTED = None


def _load_env():
    """Resolve the environment loop/env.sh sets up (it branches on
    AUTOGOD_LANE), merged over the current process environment."""
    base = dict(os.environ)
    try:
        proc = subprocess.run(
            ["bash", "-c", "set -a; source \"%s\"; env -0" % _ENV_SH],
            capture_output=True,
            env=base,
            timeout=10,
        )
        if proc.returncode == 0:
            for chunk in proc.stdout.split(b"\x00"):
                if not chunk:
                    continue
                if b"=" not in chunk:
                    continue
                k, _, v = chunk.partition(b"=")
                base[k.decode()] = v.decode()
    except Exception:
        # env.sh missing or bash unavailable: fall back to the bare process
        # environment. The driver still runs, just without the day/night
        # port selection.
        pass
    return base


def _parse_result_json(text):
    """The last JSON object in stdout (claude -p --output-format json prints
    exactly one, but be tolerant of leading log noise)."""
    text = text.strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except Exception:
        pass
    # fall back to the last top-level {...} in the text
    start = text.rfind("{")
    while start != -1:
        try:
            return json.loads(text[start:])
        except Exception:
            start = text.rfind("{", 0, start)
    return {}


def _claude_supports_max_turns(env):
    global _MAX_TURNS_SUPPORTED
    if _MAX_TURNS_SUPPORTED is not None:
        return _MAX_TURNS_SUPPORTED
    try:
        proc = subprocess.run(
            [CLAUDE_BIN, "-p", "--help"],
            capture_output=True,
            text=True,
            env=env,
            timeout=15,
        )
        help_text = (proc.stdout or "") + (proc.stderr or "")
        _MAX_TURNS_SUPPORTED = "--max-turns" in help_text
    except Exception:
        _MAX_TURNS_SUPPORTED = False
    return _MAX_TURNS_SUPPORTED


def pick(prompt):
    env = _load_env()
    env["AUTOGOD_PHASE"] = "pick"
    # Sessions are stored per cwd; --resume needs the same cwd the session
    # started in. pick() never resumes, but keep its cwd fixed to state/
    # anyway so its (unused) session storage is stable and separate from any
    # project dir.
    state_dir = env.get("AUTOGOD_STATE_DIR") or os.path.join(
        env.get("AUTOGOD_ROOT", os.path.expanduser("~/autogod-v2")), "state"
    )
    os.makedirs(state_dir, exist_ok=True)
    cmd = [CLAUDE_BIN, "-p", "--output-format", "json", "--allowedTools", ""]
    proc = subprocess.run(
        cmd,
        input=prompt,
        capture_output=True,
        text=True,
        env=env,
        cwd=state_dir,
        timeout=PICK_TIMEOUT_SECS,
    )
    obj = _parse_result_json(proc.stdout)
    return obj.get("result", "")


def build(project_dir, prompt, budget_secs, resume_session_id=None):
    env = _load_env()
    env["AUTOGOD_PHASE"] = "build"
    env["AUTOGOD_PROJECT_DIR"] = os.path.realpath(project_dir)

    cmd = [
        CLAUDE_BIN,
        "-p",
        "--output-format",
        "json",
        "--allowedTools",
        BUILD_TOOLS,
    ]
    if _claude_supports_max_turns(env):
        cmd += ["--max-turns", "40"]
    if resume_session_id:
        cmd += ["--resume", resume_session_id]

    # --resume only works when run from the same cwd the session started in
    # (sessions are stored per project dir), so build() always runs with
    # cwd=project_dir — never a bare os.getcwd().
    t0 = time.time()
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        cwd=project_dir,
    )
    killed = False
    try:
        stdout, _stderr = proc.communicate(input=prompt, timeout=budget_secs)
    except subprocess.TimeoutExpired:
        killed = True
        proc.kill()
        try:
            stdout, _stderr = proc.communicate(timeout=15)
        except Exception:
            stdout = ""
    seconds = time.time() - t0

    obj = _parse_result_json(stdout or "")
    session_id = obj.get("session_id") or resume_session_id
    if session_id:
        try:
            with open(os.path.join(project_dir, ".session"), "w") as f:
                f.write(session_id)
        except OSError:
            pass

    return {
        "session_id": session_id,
        "exit_code": -9 if killed else (proc.returncode if proc.returncode is not None else -1),
        "num_turns": obj.get("num_turns", 0),
        "is_error": True if killed else bool(obj.get("is_error", proc.returncode != 0)),
        "seconds": seconds,
    }
