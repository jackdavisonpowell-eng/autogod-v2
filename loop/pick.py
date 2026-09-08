#!/usr/bin/env python3
"""loop/pick.py — PICK phase: choose one project, or NONE. See GATE.md and
loop/prompts/pick.md (both frozen; this script only interprets them).

Usage:
    pick.py --state state/ --root /path/to/autogod-v2 [--driver mock|claude_code]

Only runs when state/current/ has no project (run.sh's job to check first;
this script also checks, defensively).
"""
import argparse
import datetime
import importlib
import json
import os
import re
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
import simpleyaml  # noqa: E402

PROBE_KINDS = {"exec", "http", "link", "file"}
REQUIRED_TOP_FIELDS = ("name", "evidence", "sentence", "outside", "probe", "milestone", "shape")
REQUIRED_PROBE_FIELDS = ("kind", "target", "keep_if")
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
FUZZY_THRESHOLD = 0.6


def parse_args(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default="state")
    ap.add_argument("--root", default=os.environ.get("AUTOGOD_ROOT", os.getcwd()))
    ap.add_argument("--driver", default=os.environ.get("AUTOGOD_DRIVER", "claude_code"))
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="run the one pick turn and validate exactly as normal, but never create "
        "state/current/ — instead append a '## Gate verdict' section to today's "
        "candidates file (see AUTOGOD_MODE=lookpick in loop/run.sh).",
    )
    return ap.parse_args(argv)


def today_str():
    return os.environ.get("AUTOGOD_TODAY") or datetime.datetime.now().strftime("%Y-%m-%d")


def log_line(state_dir, outcome, reason):
    try:
        with open(os.path.join(state_dir, "pick.log"), "a") as f:
            f.write(
                "%s\t%s\t%s\n"
                % (datetime.datetime.now().astimezone().isoformat(), outcome, reason.replace("\n", " "))
            )
    except OSError:
        pass


def existing_project(state_dir):
    current = os.path.join(state_dir, "current")
    if not os.path.isdir(current):
        return None
    for name in sorted(os.listdir(current)):
        p = os.path.join(current, name)
        if os.path.isdir(p):
            return p
    return None


def load_driver(name):
    mod = importlib.import_module("drivers.%s" % name)
    return mod


def build_prompt(root, state_dir, today):
    prompt_path = os.path.join(root, "loop", "prompts", "pick.md")
    gate_path = os.path.join(root, "GATE.md")
    dead_path = os.path.join(state_dir, "dead.md")
    cand_path = os.path.join(state_dir, "candidates", "%s.md" % today)

    def _read(p, missing_ok=False, missing_text=""):
        if not os.path.exists(p):
            if missing_ok:
                return missing_text
            raise FileNotFoundError(p)
        with open(p, encoding="utf-8") as f:
            return f.read()

    pick_md = _read(prompt_path)
    gate_md = _read(gate_path)
    dead_md = _read(dead_path, missing_ok=True, missing_text="# dead — no projects deleted yet\n")
    cand_md = _read(cand_path, missing_ok=True, missing_text="# no candidates today\n")

    prompt = (
        pick_md.rstrip()
        + "\n\n# GATE.md\n\n"
        + gate_md.rstrip()
        + "\n\n# state/dead.md\n\n"
        + dead_md.rstrip()
        + "\n\n# today's candidates\n\n"
        + cand_md.rstrip()
        + "\n"
    )
    return prompt, cand_md


def parse_none(text):
    m = re.match(r"^\s*NONE\s*:?\s*(.*)", text.strip(), re.I | re.S)
    if m and text.strip().upper().startswith("NONE"):
        return m.group(1).strip() or "(no reason given)"
    return None


def parse_pick(text):
    """Return (yaml_dict, plan_body) or raise ValueError with why."""
    m = re.search(r"```ya?ml\s*\n(.*?)```", text, re.S)
    if not m:
        raise ValueError("no ```yaml fenced block found in driver output")
    yaml_text = m.group(1)
    rest = text[m.end():]
    pm = re.search(r"---PLAN---", rest)
    if not pm:
        raise ValueError("no ---PLAN--- marker found after the yaml block")
    plan_body = rest[pm.end():].strip()
    if not plan_body:
        raise ValueError("empty PLAN.md body")
    try:
        data = simpleyaml.loads(yaml_text)
    except Exception as e:
        raise ValueError("could not parse yaml block: %s" % e)
    return data, plan_body


def validate(data, dead_shapes):
    for field in REQUIRED_TOP_FIELDS:
        if field not in data or data[field] in (None, ""):
            return "missing/empty field: %s" % field
    probe = data["probe"]
    if not isinstance(probe, dict):
        return "probe is not a mapping"
    for field in REQUIRED_PROBE_FIELDS:
        if field not in probe or probe[field] in (None, ""):
            return "missing/empty probe field: %s" % field
    if probe["kind"] not in PROBE_KINDS:
        return "probe.kind %r not in %s" % (probe["kind"], sorted(PROBE_KINDS))
    if not NAME_RE.match(data["name"]):
        return "name %r is not a kebab-slug" % data["name"]

    shape = data["shape"]
    for dead_shape, dead_line in dead_shapes:
        if _overlap(shape, dead_shape) >= FUZZY_THRESHOLD:
            return "shape fuzzy-matches dead.md line: %s" % dead_line
    return None


def _tokens(s):
    return set(re.findall(r"[a-z0-9]+", (s or "").lower()))


def _overlap(a, b):
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


def parse_dead_shapes(dead_md_text):
    out = []
    for line in dead_md_text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 3:
            out.append((parts[2], line))
    return out


def create_project(root, state_dir, data, plan_body):
    name = data["name"]
    project_dir = os.path.join(state_dir, "current", name)
    if os.path.exists(project_dir):
        raise FileExistsError(project_dir)
    os.makedirs(project_dir)

    probe = data["probe"]
    project_md = (
        "# %s\n\n"
        'evidence: "%s"\n'
        'sentence: "%s"\n'
        'outside: "%s"\n'
        "probe:\n"
        "  kind: %s\n"
        '  target: "%s"\n'
        '  keep_if: "%s"\n'
        "milestone_at:\n"
        "decided:\n"
        'next: "read PLAN.md and create run.sh that does the smallest piece"\n'
        "log:\n"
    ) % (
        name,
        data["evidence"].replace('"', "'"),
        data["sentence"].replace('"', "'"),
        data["outside"].replace('"', "'"),
        probe["kind"],
        str(probe["target"]).replace('"', "'"),
        str(probe["keep_if"]).replace('"', "'"),
    )
    with open(os.path.join(project_dir, "PROJECT.md"), "w") as f:
        f.write(project_md)

    with open(os.path.join(project_dir, "PLAN.md"), "w") as f:
        f.write(plan_body.rstrip() + "\n")

    judge_yaml = simpleyaml.dumps(
        {
            "name": name,
            "shape": data["shape"],
            "probe": {
                "kind": probe["kind"],
                "target": probe["target"],
                "keep_if": probe["keep_if"],
            },
        }
    )
    with open(os.path.join(project_dir, "judge.yaml"), "w") as f:
        f.write(judge_yaml + "\n")

    claude_dir = os.path.join(project_dir, ".claude")
    os.makedirs(claude_dir, exist_ok=True)
    guard_py = os.path.realpath(os.path.join(root, "hooks", "guard.py"))
    settings = {
        "hooks": {
            "PreToolUse": [
                {"matcher": "", "hooks": [{"type": "command", "command": guard_py}]}
            ]
        }
    }
    with open(os.path.join(claude_dir, "settings.json"), "w") as f:
        json.dump(settings, f, indent=2)
        f.write("\n")

    claude_md_target = os.path.realpath(os.path.join(root, "loop", "CLAUDE.md"))
    link_path = os.path.join(project_dir, "CLAUDE.md")
    if os.path.islink(link_path) or os.path.exists(link_path):
        os.remove(link_path)
    os.symlink(claude_md_target, link_path)

    return project_dir


def candidates_path(state_dir, today):
    return os.path.join(state_dir, "candidates", "%s.md" % today)


def append_gate_verdict(cand_path, today, would_pick, body_text):
    """--dry-run's output: a '## Gate verdict' section on today's candidates
    file with a one-line 'would have picked: <name>|NONE' plus either the
    NONE line or the parsed yaml block + PLAN body."""
    os.makedirs(os.path.dirname(cand_path), exist_ok=True)
    if not os.path.exists(cand_path):
        with open(cand_path, "w", encoding="utf-8") as f:
            f.write("# candidates — %s\n\n# no candidates today\n" % today)
    with open(cand_path, "a", encoding="utf-8") as f:
        f.write("\n## Gate verdict\n\n")
        f.write("would have picked: %s\n\n" % would_pick)
        f.write(body_text.rstrip() + "\n")


def main(argv=None):
    args = parse_args(argv)
    state_dir = args.state
    root = args.root
    dry_run = args.dry_run
    os.makedirs(state_dir, exist_ok=True)
    os.makedirs(os.path.join(state_dir, "current"), exist_ok=True)

    if not dry_run and existing_project(state_dir):
        print("pick.py: state/current already has a project, nothing to do")
        return 0

    today = today_str()
    cand_path = candidates_path(state_dir, today)

    def verdict(would_pick, body_text):
        if dry_run:
            append_gate_verdict(cand_path, today, would_pick, body_text)

    try:
        prompt, cand_md = build_prompt(root, state_dir, today)
    except FileNotFoundError as e:
        print("pick.py: missing required file: %s" % e, file=sys.stderr)
        return 2

    if cand_md.strip() in ("", "# no candidates today"):
        log_line(state_dir, "NONE", "no candidates today")
        verdict("NONE", "NONE: no candidates today")
        print("NONE: no candidates today")
        return 0

    try:
        driver = load_driver(args.driver)
    except Exception as e:
        print("pick.py: could not load driver %r: %s" % (args.driver, e), file=sys.stderr)
        return 2

    t0 = time.time()
    try:
        output = driver.pick(prompt)
    except Exception as e:
        log_line(state_dir, "ERROR", "driver.pick raised: %s" % e)
        verdict("NONE", "NONE: driver.pick failed: %s" % e)
        print("pick.py: driver.pick failed: %s" % e, file=sys.stderr)
        return 0
    seconds = time.time() - t0

    none_reason = parse_none(output)
    if none_reason is not None:
        log_line(state_dir, "NONE", none_reason)
        verdict("NONE", "NONE: %s" % none_reason)
        print("NONE: %s" % none_reason)
        return 0

    dead_path = os.path.join(state_dir, "dead.md")
    dead_text = ""
    if os.path.exists(dead_path):
        with open(dead_path, encoding="utf-8") as f:
            dead_text = f.read()
    dead_shapes = parse_dead_shapes(dead_text)

    try:
        data, plan_body = parse_pick(output)
    except ValueError as e:
        log_line(state_dir, "REFUSED", "unparseable output: %s" % e)
        verdict("NONE", "NONE: unparseable driver output: %s" % e)
        print("NONE: unparseable driver output: %s" % e)
        return 0

    why = validate(data, dead_shapes)
    if why:
        log_line(state_dir, "REFUSED", why)
        # Show what was proposed even though it was refused (dry-run wants
        # to know how close a candidate came, not just that it failed).
        verdict("NONE", "refused: %s\n\n%s" % (why, output))
        print("NONE: %s" % why)
        return 0

    if dry_run:
        log_line(state_dir, "DRY-RUN-PICKED", "%s (%.1fs)" % (data["name"], seconds))
        verdict(data["name"], output)
        print("PICKED (dry-run, not created): %s" % data["name"])
        return 0

    try:
        project_dir = create_project(root, state_dir, data, plan_body)
    except FileExistsError as e:
        log_line(state_dir, "REFUSED", "project dir already exists: %s" % e)
        print("NONE: project dir already exists: %s" % e)
        return 0

    log_line(state_dir, "PICKED", "%s (%.1fs)" % (data["name"], seconds))
    print("PICKED: %s -> %s" % (data["name"], project_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
