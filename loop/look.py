#!/usr/bin/env python3
"""loop/look.py — LOOK phase of the one loop.

Scans the vault for files that changed since the last look, pulls out lines
that read like a want/complaint/problem, and writes today's candidate list.
Vault is the only input; no WebSearch here (see GATE.md / docs/ARCHITECTURE.md).

Usage:
    look.py --vault $VAULT --state state/

Reads:  <state>/last_look          (ISO timestamp, optional; first run = 7 days back)
Writes: <state>/candidates/YYYY-MM-DD.md
        <state>/last_look          (updated to "now" at the end)
"""
import argparse
import datetime
import os
import re
import sys

MAX_CANDIDATES = 40

# Vault sub-paths scanned every pass. Directories are walked recursively for
# *.md; bare entries are single files. Edit this list, not the walking code.
VAULT_TARGETS = [
    ("dir", "Journal"),
    ("dir", "Daily"),
    ("dir", "Inbox"),
    ("file", "Inbox.md"),
    ("file", "Notepad.md"),
    ("file", os.path.join("AUTOGOD", "Notepad.md")),
    ("file", os.path.join("Infrastructure", "Loose Ends.md")),
]

# Lines that look like a want, complaint, or problem. Plain regexes, edited
# by hand — case-insensitive, matched anywhere in the line.
CANDIDATE_PATTERNS = [
    r"\bi wish\b",
    r"\bannoying\b",
    r"\bkeep forgetting\b",
    r"\bkeeps? happening\b",
    r"\bshould\b",
    r"\bneed(?:s|ed)?\b",
    r"\bwant(?:s|ed)?\b",
    r"\bbroken\b",
    r"\bevery time\b",
    r"\bhate(?:s|d)?\b",
    r"\bsucks?\b",
    r"\bfrustrat\w*\b",
    r"\bugh\b",
    r"\bwhy (?:is|isn'?t|does|doesn'?t|can'?t)\b",
    r"^\s*-\s*\[\s*\]",  # open markdown checkbox item
    r"\btodo\b",
    r"\bnever works?\b",
    r"\bstill (?:broken|doesn'?t|isn'?t)\b",
]

_PATTERNS = [re.compile(p, re.I) for p in CANDIDATE_PATTERNS]


def parse_args(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=os.environ.get("VAULT"), required=False)
    ap.add_argument("--state", default="state")
    return ap.parse_args(argv)


def read_last_look(state_dir):
    path = os.path.join(state_dir, "last_look")
    if os.path.exists(path):
        try:
            with open(path) as f:
                return datetime.datetime.fromisoformat(f.read().strip())
        except Exception:
            pass
    return datetime.datetime.now().astimezone() - datetime.timedelta(days=7)


def write_last_look(state_dir, when):
    os.makedirs(state_dir, exist_ok=True)
    with open(os.path.join(state_dir, "last_look"), "w") as f:
        f.write(when.isoformat())


def iter_target_files(vault):
    for kind, rel in VAULT_TARGETS:
        p = os.path.join(vault, rel)
        if kind == "file":
            if os.path.isfile(p):
                yield p
        else:
            if not os.path.isdir(p):
                continue
            for dirpath, _dirnames, filenames in os.walk(p):
                for fn in sorted(filenames):
                    if fn.lower().endswith(".md"):
                        yield os.path.join(dirpath, fn)


def is_candidate_line(line):
    text = line.strip()
    if not text or len(text) < 6:
        return False
    if text.startswith("#"):  # headings aren't candidates on their own
        return False
    return any(p.search(text) for p in _PATTERNS)


def extract_candidates(path, since_ts):
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return []
    if mtime <= since_ts:
        return []
    file_date = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
    out = []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError:
        return []
    for i, raw in enumerate(lines, start=1):
        line = raw.rstrip("\n")
        if is_candidate_line(line):
            out.append(
                {
                    "quote": line.strip(),
                    "path": path,
                    "line": i,
                    "date": file_date,
                    "mtime": mtime,
                }
            )
    return out


def render(candidates, today):
    parts = [
        "# candidates — %s" % today,
        "# %d candidate line(s), newest source file first, capped at %d"
        % (len(candidates), MAX_CANDIDATES),
        "",
    ]
    for c in candidates:
        parts.append('- quote: "%s"' % c["quote"].replace('"', "'"))
        parts.append("  source: %s:%d" % (c["path"], c["line"]))
        parts.append("  date: %s" % c["date"])
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def main(argv=None):
    args = parse_args(argv)
    if not args.vault:
        print("look.py: --vault (or $VAULT) is required", file=sys.stderr)
        return 2
    vault = os.path.expanduser(args.vault)
    state_dir = args.state

    since_dt = read_last_look(state_dir)
    since_ts = since_dt.timestamp()

    all_candidates = []
    for path in iter_target_files(vault):
        all_candidates.extend(extract_candidates(path, since_ts))

    # newest source file first, then earliest line first within a file
    all_candidates.sort(key=lambda c: (-c["mtime"], c["line"]))
    all_candidates = all_candidates[:MAX_CANDIDATES]

    now = datetime.datetime.now().astimezone()
    today = now.strftime("%Y-%m-%d")
    out_dir = os.path.join(state_dir, "candidates")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "%s.md" % today)
    with open(out_path, "w") as f:
        f.write(render(all_candidates, today))

    write_last_look(state_dir, now)
    print("look.py: %d candidate(s) -> %s" % (len(all_candidates), out_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
