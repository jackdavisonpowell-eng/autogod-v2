# GATE — frozen 2026-09-08

Every candidate the loop picks must pass ALL of these. The loop may not edit this file.
The only way this file changes is Jack editing it by hand.

1. **Evidence.** A quoted vault line (path + line) the candidate came from: journal, note,
   loose end. No line, no candidate.
2. **The no-AI sentence.** One sentence describing the thing with no "AI", "model",
   "agent", "LLM", "assistant" in it, that Jack would want anyway.
3. **A number with a probe.** What is measured after 7 days, the value that means keep,
   and HOW a script reads it. The probe must be one of exactly these kinds:
   - `exec`   — a command in ~/bin was run (the wrapper appends to state/usage.log)
   - `http`   — a local page was opened (the project's server writes an access log)
   - `link`   — a vault note OUTSIDE AUTOGOD/ links to the project's note
   - `file`   — a file OUTSIDE the project dir and OUTSIDE AUTOGOD/ was modified
   Anything the loop itself can produce is not a probe. No probe of these kinds = refused.
4. **Someone or something outside Jack.** Name the person or the process that would
   notice if it stopped. A cron, a server, a calendar count as a process. No stranger's
   toys: no pages for strangers, no screenshot bait, no type-a-word things.
5. **Not on the dead list.** `state/dead.md` holds every deleted project with the shape and
   the reason. Same shape = refused, no matter how the wording changed.
6. **Not coursework, not a study guide, not a chore.** Hard rule. If a chore is the useful
   thing, it is a project with a number like anything else, or it is nothing.
7. **Buildable in nights.** First milestone reachable in three nights on a 27B at 12 tok/s.
   If the plan needs a week before anything runs, cut it until it doesn't.

## Judgement (also frozen)

- Day 7 after first milestone: `judge/judge.py` reads the probe. Zero → delete the project
  dir, append one line to `state/dead.md` (date, name, shape, probe, reason), move on.
- Kept projects freeze. Changes to a kept project need the probe to prove improvement.
- The harness itself (CLAUDE.md, hooks, tool list, LOOK prompt) is a candidate like any
  other. Its probe is `bench` (the frozen 20-task eval: finished count, tool-call success
  rate, seconds). ONE change per night; keep only if finished count moves by ≥2 or
  tool-call success by ≥5 points — a 27B is noisy and "moved by one" is noise.
  `bench/tasks/` is frozen and the loop may not write there.
