# bench — AUTOGOD v2 frozen eval

Scores a headless coding harness (`claude -p`, or `dsh`) driving a slow
local 27B model on 20 fixed tasks. This is the probe for the harness
self-improvement gate (`GATE.md`): "bench" is one of the two kept-project
probes, and per the gate, `bench/tasks/` is frozen and the loop may not
write there.

## Layout

```
bench/tasks/NN-slug/
    TASK.md      the prompt given to the harness (self-contained, <=120 words,
                  names the exact output file(s))
    check.sh     exit 0 = task finished; runs INSIDE the task's working dir;
                  python3/grep/diff only, no network
    fixture/     files copied into the working dir before the run
    ARTIFACT     (most tasks) one line: the filename check.sh's primary
                  named output is; run.py checks it exists as a coarse signal
                  independent of check.sh's real correctness check
bench/drivers/
    claude_code.py   invokes `claude -p ... --output-format json`
    dsh.py           STUB: invokes `dsh --profile headless "..."`; reads
                     bench/dsh/NOTES.md if present for exact flags
bench/run.py     the runner (see below)
bench/tasks/FROZEN   date of the first baseline; nobody edits tasks/ after this
```

Tasks 01-10 are "vault chores" against a synthetic fixture vault of
markdown notes (dedupe, relative-date conversion, wikilink indexing, note
merging, frontmatter tables, missing-Hub backfill, tag rename, journal
summarisation with line citations, staleness, tag frequency). Tasks 11-20
are "small builds": each names a `run.sh` the harness must write, and
check.sh executes it (word-count CLI, static HTTP server + /health, CSV
top-3, log rotation, a Makefile `test` target, markdown->HTML, JSONL
dedupe, cron next-run, import dependency graph, checksum verifier).

Every checker verifies real content or behaviour (parses the output,
recomputes the expected answer independently, or — for the Makefile task —
mutates a copy of the working dir to prove the test target isn't a no-op).
None of them can be satisfied by merely creating an empty file.

## Running

```sh
python3 bench/run.py --driver claude-code
python3 bench/run.py --driver claude-code --tasks 01,05,12
python3 bench/run.py --driver dsh --budget-secs 600 --out /tmp/bench-out
```

Flags: `--driver {claude-code,dsh}` (required), `--tasks 01,05` (default:
all 20), `--proxy-log PATH` (default `~/autogod-v2/state/proxy.log`, the
adapter-proxy's per-request JSON log — see `proxy/adapter-proxy.py`),
`--out DIR` (default `bench/out/`), `--budget-secs N` (default 900, hard
wall-clock kill per task), `--max-turns N` (default 25, passed to the
driver; the claude-code driver only forwards `--max-turns` if the
installed CLI still supports it — some versions dropped it in favour of
`--max-budget-usd` — the wall-clock budget is the real backstop either
way).

Each task gets a fresh `--out/<task>/` working dir: fixture copied in,
`check.sh` copied in, driver invoked with `TASK.md`'s full text as the
prompt and `cwd=<workdir>`. `env` is passed straight through from the
process that invoked `run.py` — point `ANTHROPIC_BASE_URL` (or whatever
`dsh`'s config needs) at the local brain before running; `run.py` has no
opinion about which model backend is behind the driver.

## Scoring

Per task, `--out/results.jsonl` gets one line:

- `finished` — 1 if `check.sh` exited 0, else 0
- `wall_secs` — wall-clock time for the driver call
- `turns` — from the driver (claude-code: `num_turns` from
  `--output-format json`)
- `tool_calls` / `tool_errors` — claude-code: counted from the on-disk
  session transcript (`~/.claude/projects/*/<session_id>.jsonl`), counting
  `tool_use` blocks and `tool_result` blocks flagged `is_error`; falls
  back to the JSON result's `permission_denials` count, then to `null`, if
  the transcript can't be found/parsed (its format is internal to Claude
  Code and may drift across versions). dsh: heuristic regex counts over
  plain-text stdout until `bench/dsh/NOTES.md` documents a real
  machine-readable output mode.
- `tokens_in` / `tokens_out` — summed from `--proxy-log` JSON lines whose
  `ts` falls between the task's start/end timestamps (tolerates missing
  `input_tokens`/`output_tokens` fields, and an absent/empty log entirely);
  falls back to the driver's own reported usage (claude-code's
  `usage.input_tokens`/`output_tokens`) if the proxy log has nothing in
  that window (e.g. not running behind the proxy).
- `artifact_written` — whether the file named in the task's `ARTIFACT`
  (when present) exists in the workdir after the run. Coarse and
  independent of `check.sh`; two tasks (06, 07) modify existing fixture
  files in place rather than creating a new one and have no `ARTIFACT`
  file, so this is `null` for those.

`--out/TABLE.md` has the per-task table plus a summary: finished/20,
tool-call error rate (`sum(tool_errors)/sum(tool_calls)`), median
`wall_secs`, and total tokens (in+out).

## Freeze rule

`bench/tasks/FROZEN` holds the date of the first baseline run
(2026-09-08). Nobody edits `bench/tasks/` after that — same rule GATE.md
states for the harness-improvement probe: the fitness function has to stay
fixed for "did this change help" to mean anything. If a task turns out to
be genuinely broken (not just hard), fix it before the first real baseline
is recorded anywhere else (docs/bench-baseline.md); after that, treat it
like any other frozen artifact and take it to Jack.

## Verifying the checkers

Every `check.sh` was proven against a hand-made correct solution (built in
a temp dir, fixture copied in, no shortcuts) and against the bare fixture
with nothing added: 20/20 pass on the correct solution, 20/20 fail on the
empty one. The Makefile task (15) additionally proves its own checker
isn't a no-op: it mutates a copy of the solution (breaks `calc.py`) and
requires `make test` to then fail.
