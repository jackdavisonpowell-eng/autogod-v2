#!/usr/bin/env python3
"""judge/judge.py — JUDGE phase. See GATE.md ("Judgement") and
docs/ARCHITECTURE.md. Runs every pass; only acts on a project once
today >= milestone_at + 7 days.

Usage:
    judge.py --state state/ [--dry-run]

Env:
    VAULT           vault path, needed for `link` probes
    AUTOGOD_TODAY   YYYY-MM-DD override of "today", for tests
"""
import argparse
import datetime
import os
import re
import shutil
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_LOOP = os.path.join(_HERE, "..", "loop")
if _LOOP not in sys.path:
    sys.path.insert(0, _LOOP)
import simpleyaml  # noqa: E402

WINDOW_DAYS = 7


def parse_args(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default="state")
    ap.add_argument("--dry-run", action="store_true")
    return ap.parse_args(argv)


def today_date():
    override = os.environ.get("AUTOGOD_TODAY")
    if override:
        return datetime.date.fromisoformat(override.strip())
    return datetime.date.today()


def _extract_field(text, field):
    m = re.search(r"^%s:[ \t]*(.*)$" % re.escape(field), text, re.M)
    if not m:
        return ""
    v = m.group(1).strip()
    if v.startswith('"') and v.endswith('"') and len(v) >= 2:
        v = v[1:-1]
    return v


def _parse_date(s):
    s = (s or "").strip()
    if not s:
        return None
    try:
        return datetime.date.fromisoformat(s[:10])
    except ValueError:
        return None


def _parse_ts(s):
    s = (s or "").strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1]
    try:
        return datetime.datetime.fromisoformat(s)
    except ValueError:
        return None


def parse_keep_if(raw):
    """Return (op, threshold). op in {'mtime', '>=', '>'}."""
    s = (raw or "").strip()
    low = s.lower()
    if low == "mtime":
        return ("mtime", None)
    if low == "any":
        return (">=", 1)
    m = re.search(r"(>=|>)\s*(\d+)", s)
    if m:
        return (m.group(1), int(m.group(2)))
    m2 = re.search(r"(\d+)", s)
    if m2:
        return (">=", int(m2.group(1)))
    return (">=", 1)


def evaluate_keep(op, threshold, measured):
    if op == "mtime":
        return bool(measured)
    if op == ">=":
        return measured >= threshold
    if op == ">":
        return measured > threshold
    return measured >= 1


def _in_window(dt, start, end):
    return dt is not None and start <= dt < end


def measure_exec(state_dir, target, start, end):
    path = os.path.join(state_dir, "usage.log")
    if not os.path.exists(path):
        return 0
    count = 0
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            parts = line.split()
            if len(parts) < 2:
                continue
            ts_str, name = parts[0], parts[1]
            if name != target:
                continue
            if _in_window(_parse_ts(ts_str), start, end):
                count += 1
    return count


def measure_http(target, start, end):
    path = os.path.expanduser(os.path.expandvars(target or ""))
    if not path or not os.path.exists(path):
        return 0
    count = 0
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            parts = line.split()
            if not parts:
                continue
            if _in_window(_parse_ts(parts[0]), start, end):
                count += 1
    return count


def measure_link(vault, target, project_name, start, end):
    if not vault or not os.path.isdir(vault):
        return 0
    autogod_dir = os.path.realpath(os.path.join(vault, "AUTOGOD"))
    needles = []
    if target:
        needles.append("[[%s]]" % target)
    if project_name:
        needles.append(project_name)
    count = 0
    for dirpath, dirnames, filenames in os.walk(vault):
        rp = os.path.realpath(dirpath)
        if rp == autogod_dir or rp.startswith(autogod_dir + os.sep):
            dirnames[:] = []
            continue
        for fn in filenames:
            if not fn.lower().endswith(".md"):
                continue
            fp = os.path.join(dirpath, fn)
            try:
                mtime = datetime.datetime.fromtimestamp(os.path.getmtime(fp))
            except OSError:
                continue
            if not _in_window(mtime, start, end):
                continue
            try:
                with open(fp, encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except OSError:
                continue
            for needle in needles:
                count += content.count(needle)
    return count


def measure_file(target, start, end):
    path = os.path.expanduser(os.path.expandvars(target or ""))
    if not path or not os.path.exists(path):
        return 0
    mtime = datetime.datetime.fromtimestamp(os.path.getmtime(path))
    return 1 if _in_window(mtime, start, end) else 0


def _do_keep(project_dir, state_dir, name):
    kept_dir = os.path.join(state_dir, "kept")
    os.makedirs(kept_dir, exist_ok=True)
    dest = os.path.join(kept_dir, name)
    if os.path.exists(dest):
        shutil.rmtree(dest)
    shutil.move(project_dir, dest)


def _do_kill(project_dir, state_dir, name, shape, kind, measured, keep_if_raw):
    line = "%s | %s | %s | %s | measured %s, keep_if %s\n" % (
        datetime.date.today().isoformat(),
        name,
        shape or "(no shape)",
        kind,
        measured,
        keep_if_raw,
    )
    with open(os.path.join(state_dir, "dead.md"), "a") as f:
        f.write(line)
    shutil.rmtree(project_dir)


def _append_kept_md(state_dir, verdict):
    line = "%s | %s | %s | %s:%s measured=%s keep_if=%s\n" % (
        datetime.date.today().isoformat(),
        verdict["name"],
        verdict["shape"] or "(no shape)",
        verdict["probe_kind"],
        verdict["probe_target"],
        verdict["measured"],
        verdict["keep_if"],
    )
    with open(os.path.join(state_dir, "kept.md"), "a") as f:
        f.write(line)


def judge_project(project_dir, state_dir, vault, today, dry_run):
    name = os.path.basename(project_dir)
    judge_yaml_path = os.path.join(project_dir, "judge.yaml")
    project_md_path = os.path.join(project_dir, "PROJECT.md")
    if not os.path.exists(judge_yaml_path) or not os.path.exists(project_md_path):
        return {"name": name, "status": "skip", "reason": "missing judge.yaml or PROJECT.md"}

    with open(judge_yaml_path, encoding="utf-8") as f:
        jd = simpleyaml.loads(f.read())
    with open(project_md_path, encoding="utf-8") as f:
        pmd = f.read()

    milestone_raw = _extract_field(pmd, "milestone_at")
    if not milestone_raw:
        return {"name": name, "status": "waiting", "reason": "milestone not reached yet"}

    milestone_date = _parse_date(milestone_raw)
    if milestone_date is None:
        return {
            "name": name,
            "status": "skip",
            "reason": "unparseable milestone_at: %r" % milestone_raw,
        }

    judge_day = milestone_date + datetime.timedelta(days=WINDOW_DAYS)
    if today < judge_day:
        return {
            "name": name,
            "status": "waiting",
            "reason": "judged on or after %s" % judge_day.isoformat(),
        }

    probe = jd.get("probe", {})
    if not isinstance(probe, dict):
        probe = {}
    kind = probe.get("kind")
    target = probe.get("target")
    keep_if_raw = probe.get("keep_if")
    shape = jd.get("shape", "")
    proj_name = jd.get("name", name)

    window_start = datetime.datetime.combine(milestone_date, datetime.time.min)
    window_end = datetime.datetime.combine(judge_day, datetime.time.min)

    if kind == "exec":
        measured = measure_exec(state_dir, target, window_start, window_end)
    elif kind == "http":
        measured = measure_http(target, window_start, window_end)
    elif kind == "link":
        measured = measure_link(vault, target, proj_name, window_start, window_end)
    elif kind == "file":
        measured = measure_file(target, window_start, window_end)
    else:
        return {"name": name, "status": "skip", "reason": "unknown probe kind: %r" % kind}

    op, threshold = parse_keep_if(keep_if_raw)
    keep = evaluate_keep(op, threshold, measured)

    verdict = {
        "name": name,
        "status": "keep" if keep else "kill",
        "measured": measured,
        "keep_if": keep_if_raw,
        "probe_kind": kind,
        "probe_target": target,
        "shape": shape,
    }

    if dry_run:
        return verdict

    if keep:
        _append_kept_md(state_dir, verdict)
        _do_keep(project_dir, state_dir, name)
    else:
        _do_kill(project_dir, state_dir, name, shape, kind, measured, keep_if_raw)
    return verdict


def main(argv=None):
    args = parse_args(argv)
    state_dir = args.state
    vault = os.environ.get("VAULT")
    current_dir = os.path.join(state_dir, "current")
    today = today_date()

    if not os.path.isdir(current_dir):
        print("judge.py: no state/current/ directory, nothing to judge")
        return 0

    names = sorted(
        d for d in os.listdir(current_dir) if os.path.isdir(os.path.join(current_dir, d))
    )
    if not names:
        print("judge.py: no projects in state/current/")
        return 0

    for name in names:
        project_dir = os.path.join(current_dir, name)
        verdict = judge_project(project_dir, state_dir, vault, today, args.dry_run)
        print("judge.py: %s" % verdict)
    return 0


if __name__ == "__main__":
    sys.exit(main())
