"""loop/drivers/mock.py — offline driver: returns canned output from
loop/drivers/mock_fixtures/ so the whole pass can be tested without a brain,
a proxy, or network access. Same interface as loop/drivers/claude_code.py.
"""
import json
import os

_FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mock_fixtures")


def _fixture_path(name):
    return os.path.join(_FIXTURES, name)


def pick(prompt):
    fname = os.environ.get("AUTOGOD_MOCK_PICK_FIXTURE", "pick_response.txt")
    with open(_fixture_path(fname), encoding="utf-8") as f:
        return f.read()


def build(project_dir, prompt, budget_secs, resume_session_id=None):
    fname = os.environ.get("AUTOGOD_MOCK_BUILD_FIXTURE", "build_response.json")
    with open(_fixture_path(fname), encoding="utf-8") as f:
        obj = json.load(f)

    session_id = obj.get("session_id") or resume_session_id or "mock-session-1"
    try:
        with open(os.path.join(project_dir, ".session"), "w") as f:
            f.write(session_id)
    except OSError:
        pass

    return {
        "session_id": session_id,
        "exit_code": obj.get("exit_code", 0),
        "num_turns": obj.get("num_turns", 1),
        "is_error": obj.get("is_error", False),
        "seconds": obj.get("seconds", 1),
    }
