#!/usr/bin/env python3
"""judge/_read_probe.py — tiny helper for install_probe.sh: prints
"<kind>\\t<target>" for a project's judge.yaml. Not a public interface."""
import os
import sys

_LOOP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "loop")
if _LOOP not in sys.path:
    sys.path.insert(0, _LOOP)
import simpleyaml  # noqa: E402


def main():
    if len(sys.argv) != 2:
        print("usage: _read_probe.py <judge.yaml path>", file=sys.stderr)
        return 2
    with open(sys.argv[1], encoding="utf-8") as f:
        data = simpleyaml.loads(f.read())
    probe = data.get("probe", {})
    if not isinstance(probe, dict):
        probe = {}
    print("%s\t%s" % (probe.get("kind", ""), probe.get("target", "")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
