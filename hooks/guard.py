#!/usr/bin/env python3
"""PreToolUse hook — the only enforcement that isn't a prompt. See hooks/SPEC.md.

Reads one JSON object on stdin: {"tool_name": ..., "tool_input": {...}, "cwd": ...}.
Prints a deny decision and exits 0 to refuse; prints nothing and exits 0 to allow.
Fails closed: any exception anywhere -> deny with the exception text.

Config is entirely via environment (set by the driver / systemd unit):
  AUTOGOD_ROOT           repo root (contains GATE.md, bench/, hooks/, loop/, state/)
  AUTOGOD_PROJECT_DIR    state/current/<name>/ for the project currently building
  VAULT                  path to the Obsidian vault
  AUTOGOD_ALLOWED_ROOTS  colon-separated write roots; default
                         "$AUTOGOD_PROJECT_DIR:$VAULT/AUTOGOD"
  AUTOGOD_PHASE          look|pick|build — gates WebSearch/WebFetch
  AUTOGOD_STATE_DIR      default "$AUTOGOD_ROOT/state" — where guard.log lives
"""
import json
import os
import re
import shlex
import sys
import time

# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------


def _expand(p):
    return os.path.expanduser(os.path.expandvars(p))


def _rp(p):
    """Absolute, symlink-resolved path. Relative paths resolve against cwd."""
    return os.path.realpath(_expand(p))


def load_config():
    root = _rp(os.environ.get("AUTOGOD_ROOT", os.getcwd()))
    home = _rp(os.environ.get("HOME", os.path.expanduser("~")))
    vault = _rp(os.environ.get("VAULT", os.path.join(home, "vault")))
    project_dir = os.environ.get("AUTOGOD_PROJECT_DIR", "")
    project_dir = _rp(project_dir) if project_dir else ""

    allowed_env = os.environ.get("AUTOGOD_ALLOWED_ROOTS")
    if allowed_env:
        allowed_roots = [_rp(p) for p in allowed_env.split(":") if p]
    else:
        allowed_roots = []
        if project_dir:
            allowed_roots.append(project_dir)
        allowed_roots.append(_rp(os.path.join(vault, "AUTOGOD")))

    state_dir = _rp(os.environ.get("AUTOGOD_STATE_DIR", os.path.join(root, "state")))

    deny_exact = set()
    deny_prefix = []

    deny_exact.add(_rp(os.path.join(root, "GATE.md")))
    deny_prefix.append(_rp(os.path.join(root, "bench", "tasks")))
    deny_prefix.append(_rp(os.path.join(root, "hooks")))
    deny_exact.add(_rp(os.path.join(root, "loop", "CLAUDE.md")))
    deny_prefix.append(_rp(os.path.join(home, ".claude")))
    deny_prefix.append(_rp(os.path.join(home, "bin")))
    if project_dir:
        deny_exact.add(_rp(os.path.join(project_dir, ".claude", "settings.json")))

    return {
        "root": root,
        "home": home,
        "vault": vault,
        "project_dir": project_dir,
        "allowed_roots": allowed_roots,
        "state_dir": state_dir,
        "deny_exact": deny_exact,
        "deny_prefix": deny_prefix,
        "phase": os.environ.get("AUTOGOD_PHASE", ""),
    }


def _is_under(path, root):
    if not root:
        return False
    return path == root or path.startswith(root + os.sep)


def _log_deny(cfg, tool, reason, offending):
    try:
        os.makedirs(cfg["state_dir"], exist_ok=True)
        line = "%s\t%s\t%s\t%s\n" % (
            time.strftime("%Y-%m-%dT%H:%M:%S"),
            tool,
            reason,
            offending,
        )
        with open(os.path.join(cfg["state_dir"], "guard.log"), "a") as f:
            f.write(line)
    except Exception:
        # logging must never be the reason a deny fails to happen
        pass


# ---------------------------------------------------------------------------
# path-writing tools: Write / Edit / MultiEdit / NotebookEdit
# ---------------------------------------------------------------------------


def _extract_path(tool_input):
    for key in ("file_path", "notebook_path", "path"):
        v = tool_input.get(key)
        if isinstance(v, str) and v:
            return v
    return None


def check_write_path(raw_path, cwd, cfg):
    """Return (deny: bool, reason: str, resolved: str)."""
    if not cwd:
        cwd = cfg["root"]
    p = _expand(raw_path)
    if not os.path.isabs(p):
        p = os.path.join(cwd, p)
    resolved = os.path.realpath(p)

    if resolved in cfg["deny_exact"]:
        return True, "denied path: %s" % resolved, resolved
    for pref in cfg["deny_prefix"]:
        if _is_under(resolved, pref):
            return True, "denied path (protected area): %s" % resolved, resolved
    # settings.json anywhere under a .claude dir inside the project is denied too
    if os.path.basename(resolved) == "settings.json" and os.path.basename(
        os.path.dirname(resolved)
    ) == ".claude":
        return True, "denied path: %s" % resolved, resolved

    for root in cfg["allowed_roots"]:
        if _is_under(resolved, root):
            return False, "", resolved

    return True, "outside allowed write roots: %s" % resolved, resolved


# ---------------------------------------------------------------------------
# read-only tools: Read / Grep / Glob
# ---------------------------------------------------------------------------

_READ_DENY_BASENAME_PATTERNS = [
    re.compile(r".*\.env$", re.I),
    re.compile(r".*token.*", re.I),
    re.compile(r".*secret.*", re.I),
    re.compile(r".*\.pem$", re.I),
    re.compile(r"^id_.*", re.I),
]


def check_read_path(raw_path, cwd, cfg):
    if not cwd:
        cwd = cfg["root"]
    p = _expand(raw_path)
    if not os.path.isabs(p):
        p = os.path.join(cwd, p)
    resolved = os.path.realpath(p)

    if _is_under(resolved, _rp(os.path.join(cfg["home"], ".ssh"))):
        return True, "denied path: %s" % resolved, resolved
    if resolved == _rp(os.path.join(cfg["home"], ".claude", "notify.env")):
        return True, "denied path: %s" % resolved, resolved

    base = os.path.basename(resolved)
    for pat in _READ_DENY_BASENAME_PATTERNS:
        if pat.match(base):
            return True, "denied path (secret-shaped name): %s" % resolved, resolved

    if _is_under(resolved, cfg["home"]) or _is_under(resolved, cfg["vault"]):
        return False, "", resolved

    return True, "outside $HOME and $VAULT: %s" % resolved, resolved


# ---------------------------------------------------------------------------
# Bash
# ---------------------------------------------------------------------------

# Words that are never legitimate for this builder in any form: bare, path-
# prefixed (/usr/bin/sudo), or buried inside a quoted literal that shlex
# mangles when it re-tokenizes a nested -c/-e body (e.g. python's
# ["ssh","host","cmd"] collapses to one token, but the word "ssh" is still
# there). A plain \b...\b scan over the RAW command text catches all three
# shapes and doesn't depend on tokenization succeeding at all.
_ALWAYS_DENIED_WORDS_RE = re.compile(r"\b(sudo|systemctl|ssh|scp|crontab|eval)\b")
_GIT_PUSH_RE = re.compile(r"\bgit\s+push\b")

_INTERPRETER_RE = re.compile(r"^(bash|sh|zsh|dash|python[0-9.]*|perl[0-9.]*|node|ruby)$")

_CONTROL_TOKENS = ("|", "&&", "||", ";")

# Commands whose destination argument must resolve under an allowed root.
_DEST_COMMANDS = {"cp", "mv", "install", "ln", "rsync", "dd", "tar", "unzip", "git"}


def _cmdnames(toks):
    """Basename of every token that looks like a path (has a '/'); every
    other token is left as-is. Use this, not raw tokens, to identify a
    *command name* — /usr/bin/sudo must be caught exactly like sudo."""
    return [os.path.basename(t) if "/" in t and not t.startswith(("-", ">", "<")) else t for t in toks]


def _has_rm_rf_root(toks, btoks):
    if "rm" not in btoks:
        return False
    has_r = any(t in ("-r", "-rf", "-fr", "-R", "-Rf", "-fR") or
                (t.startswith("-") and "r" in t.lower() and "f" in t.lower())
                for t in toks)
    has_f = any(t in ("-f", "-rf", "-fr") or (t.startswith("-") and "f" in t.lower())
                for t in toks)
    return has_r and has_f and "/" in toks


def _has_chmod_setid(toks, btoks):
    if "chmod" not in btoks:
        return False
    return any(re.search(r"\+s", t) for t in toks[btoks.index("chmod") + 1:])


_DEV_SD_RE = re.compile(r"(?:^|=)/dev/sd\w*")


def _has_dev_sd_write(toks):
    for i, t in enumerate(toks):
        if t in (">", ">>") and i + 1 < len(toks) and toks[i + 1].startswith("/dev/sd"):
            return True
        if _DEV_SD_RE.search(t):
            return True
    return False


def _has_rsync_remote(toks, btoks):
    if "rsync" not in btoks:
        return False
    for t in toks[btoks.index("rsync") + 1:]:
        if t.startswith("-"):
            continue
        # host:path or user@host:path, but not a bare local absolute path
        if ":" in t and not t.startswith("/"):
            return True
    return False


def _has_nvidia_smi_reset(toks, btoks):
    return "nvidia-smi" in btoks and "-r" in toks


def _has_kill_all(toks, btoks):
    return "kill" in btoks and "-9" in toks and "-1" in toks


def _has_crontab(btoks):
    # covered by _ALWAYS_DENIED_WORDS_RE too, kept for basename-prefixed form
    return "crontab" in btoks


_LOCAL_HOSTS = {"127.0.0.1"}


def _extract_host(token):
    t = token
    if "://" in t:
        t = t.split("://", 1)[1]
    t = t.split("/", 1)[0]
    t = t.split("@")[-1]
    host = t.split(":")[0]
    return host


def _looks_like_url_token(t):
    if t.startswith("-"):
        return False
    if "://" in t:
        return True
    head = t.split("/", 1)[0].split(":")[0].split("@")[-1]
    if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", head):
        return True
    if "." in head or head == "localhost":
        return True
    return False


def _has_curl_wget_outside(toks, btoks):
    for tool in ("curl", "wget"):
        if tool not in btoks:
            continue
        idx = btoks.index(tool)
        for t in toks[idx + 1:]:
            if t in _CONTROL_TOKENS:
                break
            if _looks_like_url_token(t):
                host = _extract_host(t)
                if host not in _LOCAL_HOSTS:
                    return True, "%s to non-local host: %s" % (tool, host)
    return False, ""


def _has_encoded_payload_smuggling(toks, btoks):
    if "base64" in btoks:
        for a in toks[btoks.index("base64") + 1:]:
            if a in ("-d", "--decode") or a.startswith("--decode"):
                return True, "base64 -d/--decode"
    if "xxd" in btoks:
        for a in toks[btoks.index("xxd") + 1:]:
            if a == "-r":
                return True, "xxd -r"
    if "printf" in btoks:
        for a in toks:
            if re.search(r"\\x[0-9a-fA-F]{2}", a):
                return True, "printf with \\x escape"
    return False, ""


def _has_pipe_to_interpreter(toks, btoks):
    for i, t in enumerate(btoks):
        if t != "|" or i + 1 >= len(btoks):
            continue
        nxt = btoks[i + 1]
        if _INTERPRETER_RE.match(nxt):
            return True, "pipe into interpreter: %s" % nxt
        if nxt == "xargs":
            for j in range(i + 2, len(btoks)):
                if btoks[j] in _CONTROL_TOKENS:
                    break
                if _INTERPRETER_RE.match(btoks[j]):
                    return True, "pipe into xargs -> interpreter: %s" % btoks[j]
    return False, ""


def _resolve_for_bash(path_tok, cwd, cfg):
    p = _expand(path_tok)
    if not os.path.isabs(p):
        p = os.path.join(cwd or cfg["root"], p)
    return os.path.realpath(p)


def _outside_roots(path_tok, cwd, cfg):
    resolved = _resolve_for_bash(path_tok, cwd, cfg)
    return not any(_is_under(resolved, r) for r in cfg["allowed_roots"]), resolved


def _has_redirect_outside_roots(toks, cwd, cfg):
    for i, t in enumerate(toks):
        if t in (">", ">>") and i + 1 < len(toks):
            target = toks[i + 1]
            if target in ("/dev/null", "&1", "&2"):
                continue
            bad, resolved = _outside_roots(target, cwd, cfg)
            if bad:
                return True, "redirect outside allowed roots: %s" % resolved
        if t == "tee":
            for t2 in toks[i + 1:]:
                if t2 in _CONTROL_TOKENS:
                    break
                if t2.startswith("-"):
                    continue
                bad, resolved = _outside_roots(t2, cwd, cfg)
                if bad:
                    return True, "tee outside allowed roots: %s" % resolved
    return False, ""


def _has_cd_outside_then_write(toks, btoks, cwd, cfg):
    cd_outside_at = None
    for i, t in enumerate(btoks):
        if t == "cd" and i + 1 < len(toks):
            bad, _resolved = _outside_roots(toks[i + 1], cwd, cfg)
            cd_outside_at = i if bad else None
        elif cd_outside_at is not None and t in (">", ">>", "tee"):
            return True, "cd outside roots followed by a write"
    return False, ""


def _has_source_outside_roots(toks, btoks, cwd, cfg):
    for i, t in enumerate(btoks):
        if t == "source" and i + 1 < len(toks):
            bad, resolved = _outside_roots(toks[i + 1], cwd, cfg)
            if bad:
                return True, "source outside allowed roots: %s" % resolved
        elif toks[i] == "." and i + 1 < len(toks) and (i == 0 or toks[i - 1] in _CONTROL_TOKENS):
            bad, resolved = _outside_roots(toks[i + 1], cwd, cfg)
            if bad:
                return True, "'.' (source) outside allowed roots: %s" % resolved
    return False, ""


def _split_commands(toks, btoks):
    """Split on control tokens into (toks, btoks) sub-command slices, so
    destination-argument checks look at one command's own arguments only."""
    cmds = []
    cur_t, cur_b = [], []
    for t, b in zip(toks, btoks):
        if t in _CONTROL_TOKENS:
            if cur_t:
                cmds.append((cur_t, cur_b))
            cur_t, cur_b = [], []
        else:
            cur_t.append(t)
            cur_b.append(b)
    if cur_t:
        cmds.append((cur_t, cur_b))
    return cmds


def _dest_check_one(sub_toks, sub_btoks, cwd, cfg):
    if not sub_btoks:
        return False, ""
    cmd = sub_btoks[0]
    if cmd not in _DEST_COMMANDS:
        return False, ""
    args = sub_toks[1:]
    bargs = sub_btoks[1:]

    def check(dest, label):
        bad, resolved = _outside_roots(dest, cwd, cfg)
        if bad:
            return True, "%s destination outside allowed roots: %s" % (label, resolved)
        return False, ""

    if cmd in ("cp", "mv", "install", "ln"):
        dest = None
        for i, a in enumerate(args):
            if a in ("-t", "--target-directory") and i + 1 < len(args):
                dest = args[i + 1]
            elif a.startswith("--target-directory="):
                dest = a.split("=", 1)[1]
        if dest is None:
            positional = [a for a in args if not a.startswith("-")]
            if len(positional) >= 2:
                dest = positional[-1]
        if dest is not None:
            return check(dest, cmd)

    elif cmd == "rsync":
        positional = [a for a in args if not a.startswith("-")]
        if positional:
            dest = positional[-1]
            if ":" not in dest or dest.startswith("/"):
                return check(dest, "rsync")

    elif cmd == "dd":
        for a in args:
            if a.startswith("of=") and a[3:] != "/dev/null":
                return check(a[3:], "dd")

    elif cmd == "tar":
        cdir = None
        for i, a in enumerate(args):
            if a == "-C" and i + 1 < len(args):
                cdir = args[i + 1]
        extracting = any(
            a in ("-x", "--extract") or (a.startswith("-") and not a.startswith("--") and "x" in a[1:])
            for a in args
        )
        if extracting:
            return check(cdir if cdir is not None else (cwd or cfg["root"]), "tar")

    elif cmd == "unzip":
        for i, a in enumerate(args):
            if a == "-d" and i + 1 < len(args):
                return check(args[i + 1], "unzip")

    elif cmd == "git":
        if bargs[:1] == ["clone"]:
            positional = [a for a in args[1:] if not a.startswith("-")]
            if len(positional) >= 2:
                return check(positional[-1], "git clone")
            return check(cwd or cfg["root"], "git clone")
        if bargs[:2] == ["worktree", "add"]:
            positional = [a for a in args[2:] if not a.startswith("-")]
            if positional:
                return check(positional[0], "git worktree add")

    return False, ""


def _has_write_dest_outside_roots(toks, btoks, cwd, cfg):
    for sub_toks, sub_btoks in _split_commands(toks, btoks):
        bad, why = _dest_check_one(sub_toks, sub_btoks, cwd, cfg)
        if bad:
            return True, why
    return False, ""


def _tokenize(command):
    lex = shlex.shlex(command, posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    return list(lex)


def check_bash(command, cwd, cfg, _depth=0):
    # Raw-text word scan first: independent of tokenization, so it still
    # catches a denied word buried inside a quoted literal that shlex
    # collapses when re-parsing a nested -c/-e body (see _cmdnames docstring).
    m = _ALWAYS_DENIED_WORDS_RE.search(command)
    if m:
        return True, "denied token: %s" % m.group(1)
    if _GIT_PUSH_RE.search(command):
        return True, "denied token: git push"

    try:
        toks = _tokenize(command)
    except ValueError as e:
        # unbalanced quotes etc: fail closed
        return True, "unparseable command (%s): %s" % (e, command)

    btoks = _cmdnames(toks)

    if _has_rm_rf_root(toks, btoks):
        return True, "denied: rm -rf /"
    if _has_chmod_setid(toks, btoks):
        return True, "denied: chmod +s"
    if _has_dev_sd_write(toks):
        return True, "denied: write to /dev/sd*"
    if _has_rsync_remote(toks, btoks):
        return True, "denied: rsync to a remote host"
    if _has_nvidia_smi_reset(toks, btoks):
        return True, "denied: nvidia-smi -r"
    if _has_kill_all(toks, btoks):
        return True, "denied: kill -9 -1"
    if _has_crontab(btoks):
        return True, "denied: crontab"

    bad, why = _has_curl_wget_outside(toks, btoks)
    if bad:
        return True, "denied: " + why

    bad, why = _has_encoded_payload_smuggling(toks, btoks)
    if bad:
        return True, "denied: " + why

    bad, why = _has_pipe_to_interpreter(toks, btoks)
    if bad:
        return True, "denied: " + why

    bad, why = _has_redirect_outside_roots(toks, cwd, cfg)
    if bad:
        return True, "denied: " + why

    bad, why = _has_cd_outside_then_write(toks, btoks, cwd, cfg)
    if bad:
        return True, "denied: " + why

    bad, why = _has_source_outside_roots(toks, btoks, cwd, cfg)
    if bad:
        return True, "denied: " + why

    bad, why = _has_write_dest_outside_roots(toks, btoks, cwd, cfg)
    if bad:
        return True, "denied: " + why

    # python -c / bash -c / sh -c bodies (and any nested quoted sub-command
    # inside them) collapse to a single token that still contains whitespace.
    # Recurse into those and apply every rule above to them too.
    if _depth < 6:
        for t in toks:
            if " " in t or "\t" in t:
                bad, why = check_bash(t, cwd, cfg, _depth=_depth + 1)
                if bad:
                    return True, "denied in nested command body: " + why

    return False, ""


# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------

_WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
_READ_TOOLS = {"Read", "Grep", "Glob"}
_WEB_TOOLS = {"WebSearch", "WebFetch"}


def decide(payload, cfg):
    """Return (deny: bool, reason: str)."""
    tool_name = payload.get("tool_name")
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}
    cwd = payload.get("cwd") or cfg["root"]

    if tool_name in _WRITE_TOOLS:
        raw = _extract_path(tool_input)
        if raw is None:
            return True, "no path in tool_input for %s" % tool_name
        deny, reason, _ = check_write_path(raw, cwd, cfg)
        return deny, reason

    if tool_name == "Bash":
        command = tool_input.get("command")
        if not isinstance(command, str) or not command.strip():
            return True, "no command in tool_input for Bash"
        return check_bash(command, cwd, cfg)

    if tool_name in _READ_TOOLS:
        raw = _extract_path(tool_input) or tool_input.get("path")
        if raw is None:
            # e.g. Grep with only a pattern and no path: nothing to check
            return False, ""
        deny, reason, _ = check_read_path(raw, cwd, cfg)
        return deny, reason

    if tool_name in _WEB_TOOLS:
        if cfg.get("phase") != "build":
            return True, "%s only allowed when AUTOGOD_PHASE=build" % tool_name
        return False, ""

    return False, ""


def main():
    cfg = None
    tool_name = "?"
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("hook payload is not a JSON object")
        tool_name = payload.get("tool_name", "?")
        cfg = load_config()
        deny, reason = decide(payload, cfg)
    except Exception as e:
        deny, reason = True, "guard exception: %s: %s" % (type(e).__name__, e)
        if cfg is None:
            try:
                cfg = load_config()
            except Exception:
                cfg = None

    if deny:
        if cfg is not None:
            _log_deny(cfg, tool_name, reason, "")
        out = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }
        print(json.dumps(out))
    # allow: print nothing
    sys.exit(0)


if __name__ == "__main__":
    main()
