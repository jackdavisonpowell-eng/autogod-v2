"""loop/simpleyaml.py — a tiny YAML-subset parser, stdlib only.

Handles exactly the shape the loop needs: flat `key: value` mappings with at
most one level of nesting (used for the `probe:` block), scalar values that
are either double-quoted strings (with \\" and \\\\ escapes) or bare text,
and `# comment` stripped when it isn't inside quotes. That is the entire
grammar loop/prompts/pick.md asks the model to produce and judge.yaml uses.
Not a general YAML parser — do not feed it anything else.
"""


def _parse_scalar(s):
    s = s.strip()
    if s.startswith('"'):
        buf = []
        i = 1
        while i < len(s):
            c = s[i]
            if c == "\\" and i + 1 < len(s):
                buf.append(s[i + 1])
                i += 2
                continue
            if c == '"':
                break
            buf.append(c)
            i += 1
        return "".join(buf)
    if "#" in s:
        s = s.split("#", 1)[0]
    return s.strip()


def loads(text):
    """Parse a flat-or-one-level-nested mapping. Returns a dict."""
    root = {}
    stack = [(-1, root)]
    for raw in text.split("\n"):
        if not raw.strip():
            continue
        stripped = raw.strip()
        if stripped.startswith("#"):
            continue
        if ":" not in raw:
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        while len(stack) > 1 and stack[-1][0] >= indent:
            stack.pop()
        parent = stack[-1][1]
        key, _, rest = stripped.partition(":")
        key = key.strip()
        rest = rest.strip()
        if rest == "":
            child = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = _parse_scalar(rest)
    return root


def dumps(obj, indent=0):
    """Render a dict back to the same subset (2-space nesting, quoted
    strings). Good enough for judge.yaml; not meant to round-trip anything
    fancier."""
    lines = []
    pad = "  " * indent
    for k, v in obj.items():
        if isinstance(v, dict):
            lines.append("%s%s:" % (pad, k))
            lines.append(dumps(v, indent + 1))
        else:
            lines.append('%s%s: "%s"' % (pad, k, str(v).replace('"', "'")))
    return "\n".join(lines)
