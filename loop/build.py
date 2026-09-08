#!/usr/bin/env python3
"""loop/build.py — BUILD phase: one driver turn inside an existing project.

Thin wrapper so loop/run.sh (bash) can call the pluggable Python driver.
Resumes the project's saved session (project_dir/.session) when present.

Usage:
    build.py --project-dir state/current/<name> --budget-secs 3600 --prompt "..."
             [--driver mock|claude_code]
"""
import argparse
import importlib
import json
import os
import sys


def parse_args(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-dir", required=True)
    ap.add_argument("--budget-secs", type=int, required=True)
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--driver", default=os.environ.get("AUTOGOD_DRIVER", "claude_code"))
    return ap.parse_args(argv)


def load_driver(name):
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    return importlib.import_module("drivers.%s" % name)


def read_session(project_dir):
    p = os.path.join(project_dir, ".session")
    if os.path.exists(p):
        with open(p) as f:
            sid = f.read().strip()
            return sid or None
    return None


def main(argv=None):
    args = parse_args(argv)
    project_dir = args.project_dir
    if not os.path.isdir(project_dir):
        print("build.py: no such project dir: %s" % project_dir, file=sys.stderr)
        return 2

    try:
        driver = load_driver(args.driver)
    except Exception as e:
        print("build.py: could not load driver %r: %s" % (args.driver, e), file=sys.stderr)
        return 2

    resume_id = read_session(project_dir)
    try:
        result = driver.build(project_dir, args.prompt, args.budget_secs, resume_id)
    except Exception as e:
        print("build.py: driver.build raised: %s" % e, file=sys.stderr)
        return 1

    print(json.dumps(result))
    return 0 if not result.get("is_error") else 1


if __name__ == "__main__":
    sys.exit(main())
