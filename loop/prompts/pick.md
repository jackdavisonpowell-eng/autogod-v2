You are picking ONE project for AUTOGOD v2, or none. Below is GATE.md (the rules, frozen),
then dead.md (every deleted project — same shape is refused), then today's candidate list,
each with the vault line it came from.

Output EXACTLY one of:

NONE: <one line why nothing passes>

or a fenced block:

```yaml
name: <kebab-slug>
evidence: "<quoted vault line>"  # path:line
sentence: "<the no-AI sentence>"
outside: "<person or process that would notice>"
probe:
  kind: exec|http|link|file
  target: "<the ~/bin name, the log path, the note name, or the file path>"
  keep_if: "<the number and the value that means keep, e.g. '>=3 runs in 7 days'>"
milestone: "<what works end to end after at most three nights>"
shape: "<one-line shape, for dead.md comparison>"
```

Then a PLAN.md body after a line `---PLAN---`: what, for whom, the number, the first
milestone, the files it will consist of (≤6). Under 40 lines. No features past the milestone.

Refuse anything that is coursework, a study guide, a chore with no number, a page for
strangers, or the same shape as a dead.md line. When in doubt, NONE. A NONE costs nothing;
a wrong pick costs seven nights.
