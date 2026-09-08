#!/usr/bin/env python3
"""bench/run.py -- AUTOGOD v2 frozen eval runner.

Drives a headless coding harness (Claude Code `claude -p`, or DeepSeek
Harness `dsh`) through the 20 frozen tasks in bench/tasks/, scores each
against its check.sh, and writes bench/out/results.jsonl + TABLE.md.

Usage:
    python3 bench/run.py --driver claude-code
    python3 bench/run.py --driver claude-code --tasks 01,05,12
    python3 bench/run.py --driver dsh --out /tmp/bench-out --budget-secs 600

See bench/README.md for full docs. Python 3 stdlib only.
"""
import argparse
import datetime
import importlib.util
import json
import os
import shutil
import statistics
import subprocess
import sys

BENCH_DIR = os.path.dirname(os.path.abspath(__file__))
TASKS_DIR = os.path.join(BENCH_DIR, "tasks")
DRIVERS_DIR = os.path.join(BENCH_DIR, "drivers")

DRIVER_FILES = {
    "claude-code": "claude_code.py",
    "dsh": "dsh.py",
}

TS_FMT = "%Y-%m-%dT%H:%M:%S"


def load_driver(name):
    fn = DRIVER_FILES.get(name)
    if not fn:
        sys.exit(f"unknown driver {name!r}; choices: {sorted(DRIVER_FILES)}")
    path = os.path.join(DRIVERS_DIR, fn)
    spec = importlib.util.spec_from_file_location(f"bench_driver_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def list_tasks():
    out = []
    for entry in sorted(os.listdir(TASKS_DIR)):
        p = os.path.join(TASKS_DIR, entry)
        if os.path.isdir(p) and os.path.exists(os.path.join(p, "TASK.md")):
            out.append(entry)
    return out


def filter_tasks(all_tasks, wanted):
    if not wanted:
        return all_tasks
    ids = {w.strip().zfill(2) for w in wanted.split(",") if w.strip()}
    picked = [t for t in all_tasks if t.split("-", 1)[0] in ids]
    missing = ids - {t.split("-", 1)[0] for t in picked}
    if missing:
        sys.exit(f"no task(s) matching id(s): {sorted(missing)}")
    return picked


def fresh_workdir(out_dir, task):
    d = os.path.join(out_dir, task)
    if os.path.exists(d):
        shutil.rmtree(d)
    os.makedirs(d)
    fixture = os.path.join(TASKS_DIR, task, "fixture")
    if os.path.isdir(fixture):
        for item in os.listdir(fixture):
            s = os.path.join(fixture, item)
            t = os.path.join(d, item)
            if os.path.isdir(s):
                shutil.copytree(s, t)
            else:
                shutil.copy2(s, t)
    # check.sh runs inside the task's working dir (per bench/README.md)
    shutil.copy2(os.path.join(TASKS_DIR, task, "check.sh"), os.path.join(d, "check.sh"))
    return d


def read_artifact_name(task):
    p = os.path.join(TASKS_DIR, task, "ARTIFACT")
    if os.path.exists(p):
        return open(p).read().strip()
    return None


def parse_proxy_tokens(proxy_log_path, start_dt, end_dt):
    """Sum input_tokens/output_tokens from proxy log lines whose ts falls
    within [start_dt, end_dt]. Tolerates missing fields/lines entirely."""
    tokens_in = tokens_out = 0
    seen_any = False
    if not proxy_log_path or not os.path.exists(proxy_log_path):
        return None, None
    try:
        with open(proxy_log_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                ts = rec.get("ts")
                if not ts:
                    continue
                try:
                    ts_dt = datetime.datetime.strptime(ts, TS_FMT)
                except Exception:
                    continue
                if not (start_dt <= ts_dt <= end_dt):
                    continue
                seen_any = True
                if "input_tokens" in rec:
                    tokens_in += rec["input_tokens"]
                if "output_tokens" in rec:
                    tokens_out += rec["output_tokens"]
    except Exception:
        return None, None
    if not seen_any:
        return None, None
    return tokens_in, tokens_out


def run_check(workdir, timeout=60):
    try:
        r = subprocess.run(
            ["sh", "check.sh"], cwd=workdir,
            capture_output=True, text=True, timeout=timeout,
        )
        return r.returncode, (r.stdout + r.stderr)
    except subprocess.TimeoutExpired:
        return 124, "check.sh timed out"
    except Exception as e:
        return 1, f"check.sh error: {e}"


def run_one(driver_mod, task, out_dir, budget_secs, max_turns, proxy_log, env):
    workdir = fresh_workdir(out_dir, task)
    task_md_path = os.path.join(TASKS_DIR, task, "TASK.md")
    prompt = open(task_md_path).read()

    started_at = datetime.datetime.now()
    result = driver_mod.run(
        prompt=prompt, cwd=workdir, budget_secs=budget_secs,
        max_turns=max_turns, env=env,
    )
    ended_at = datetime.datetime.now()

    check_rc, check_out = run_check(workdir)
    finished = 1 if check_rc == 0 else 0

    artifact_name = read_artifact_name(task)
    artifact_written = None
    if artifact_name:
        artifact_written = os.path.exists(os.path.join(workdir, artifact_name))

    tokens_in, tokens_out = parse_proxy_tokens(proxy_log, started_at, ended_at)
    if tokens_in is None:
        tokens_in = result.get("tokens_in")
    if tokens_out is None:
        tokens_out = result.get("tokens_out")

    row = {
        "task": task,
        "finished": finished,
        "wall_secs": result.get("wall_secs"),
        "turns": result.get("turns"),
        "tool_calls": result.get("tool_calls"),
        "tool_errors": result.get("tool_errors"),
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "artifact_name": artifact_name,
        "artifact_written": artifact_written,
        "exit_code": result.get("exit_code"),
        "budget_secs": budget_secs,
        "max_turns": max_turns,
        "started_at": started_at.strftime(TS_FMT),
        "ended_at": ended_at.strftime(TS_FMT),
        "workdir": workdir,
        "check_exit_code": check_rc,
        "check_output": check_out.strip()[:2000],
    }
    return row


def write_table(rows, driver, out_dir):
    lines = []
    lines.append(f"# bench results -- driver={driver}\n")
    lines.append(f"Generated {datetime.datetime.now().strftime(TS_FMT)}\n")
    lines.append("| task | finished | wall_secs | turns | tool_calls | tool_errors | tokens_in | tokens_out | artifact |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in rows:
        art = "-" if r["artifact_name"] is None else ("yes" if r["artifact_written"] else "MISSING")
        lines.append(
            f"| {r['task']} | {'PASS' if r['finished'] else 'FAIL'} | {r['wall_secs']} | "
            f"{r['turns']} | {r['tool_calls']} | {r['tool_errors']} | "
            f"{r['tokens_in']} | {r['tokens_out']} | {art} |"
        )

    n = len(rows)
    finished_n = sum(r["finished"] for r in rows)
    walls = [r["wall_secs"] for r in rows if isinstance(r["wall_secs"], (int, float))]
    median_wall = statistics.median(walls) if walls else None
    tc_total = sum(r["tool_calls"] for r in rows if isinstance(r["tool_calls"], int))
    te_total = sum(r["tool_errors"] for r in rows if isinstance(r["tool_errors"], int))
    tc_err_rate = (te_total / tc_total) if tc_total else None
    tok_total = sum(
        (r["tokens_in"] or 0) + (r["tokens_out"] or 0) for r in rows
    )

    lines.append("")
    lines.append("## Summary")
    lines.append(f"- finished: {finished_n}/{n}")
    lines.append(
        "- tool-call error rate: "
        + (f"{tc_err_rate:.1%} ({te_total}/{tc_total})" if tc_err_rate is not None else "n/a")
    )
    lines.append(f"- median wall_secs: {median_wall}")
    lines.append(f"- total tokens (in+out): {tok_total}")

    with open(os.path.join(out_dir, "TABLE.md"), "w") as f:
        f.write("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--driver", required=True, choices=sorted(DRIVER_FILES))
    ap.add_argument("--tasks", default=None, help="comma list of task ids, e.g. 01,05,12 (default: all)")
    ap.add_argument("--proxy-log", default=os.path.expanduser("~/autogod-v2/state/proxy.log"))
    ap.add_argument("--out", default=os.path.join(BENCH_DIR, "out"))
    ap.add_argument("--budget-secs", type=int, default=900)
    ap.add_argument("--max-turns", type=int, default=25)
    args = ap.parse_args()

    driver_mod = load_driver(args.driver)
    all_tasks = list_tasks()
    tasks = filter_tasks(all_tasks, args.tasks)
    if not tasks:
        sys.exit("no tasks found under bench/tasks/")

    os.makedirs(args.out, exist_ok=True)
    env = os.environ.copy()

    rows = []
    results_path = os.path.join(args.out, "results.jsonl")
    with open(results_path, "w") as rf:
        for task in tasks:
            print(f"[{task}] running ({args.driver}, budget={args.budget_secs}s)...", file=sys.stderr)
            row = run_one(
                driver_mod, task, args.out, args.budget_secs,
                args.max_turns, args.proxy_log, env,
            )
            row["driver"] = args.driver
            rows.append(row)
            rf.write(json.dumps(row) + "\n")
            rf.flush()
            status = "PASS" if row["finished"] else "FAIL"
            print(f"[{task}] {status} wall={row['wall_secs']}s turns={row['turns']}", file=sys.stderr)

    write_table(rows, args.driver, args.out)
    print(f"\nwrote {results_path}", file=sys.stderr)
    print(f"wrote {os.path.join(args.out, 'TABLE.md')}", file=sys.stderr)


if __name__ == "__main__":
    main()
