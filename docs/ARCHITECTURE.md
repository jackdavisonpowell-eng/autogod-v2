# AUTOGOD v2 — architecture (2026-09-08)

One loop, one process, one project at a time. Local brain, no API tokens.
Spec: vault Infrastructure/AUTOGOD v2 — One Loop on Claude Code.md. Gate: GATE.md (frozen).

## Boxes
- Runs on thebeast as user jack (uid separation is a later hardening step, see dead-ends).
- Brain: day = P100 pair :11466 (llama.cpp, Qwen3.8-27B); night = V100 copy on :11467.
- FRIDAY owns the V100 by day (:11460). Never touch it by day.
- Harness = Claude Code headless (`claude -p`) via proxy/adapter-proxy.py on :11499,
  unless the bench (bench/) says DeepSeek Harness wins. Driver is pluggable: loop/drivers/.

## Layout
```
proxy/      adapter-proxy.py + systemd user unit (autogod-v2-proxy.service)
bench/      FROZEN eval set: tasks/<nn>-<slug>/{TASK.md,check.sh,fixture/}, run.py, drivers
loop/       run.sh (one pass), look.py, pick.py, CLAUDE.md (rules for the brain), prompts/
hooks/      guard.py — PreToolUse: deny writes outside project dir + vault/AUTOGOD/,
            deny systemctl/sudo/git push/ssh/curl-to-outside; deny writes to bench/tasks, GATE.md
judge/      judge.py — reads probes, kills at day 7, writes state/dead.md
state/      current/ (PROJECT.md, PLAN.md, judge.yaml, session id), dead.md, usage.log,
            candidates/<date>.md, kept/<name>/
docs/       this file, bench tables (also copied to vault AUTOGOD/bench/)
```

## One pass (loop/run.sh, systemd timer, nightly + one day pass)
```
LOOK   look.py: vault files changed since state/last_look (Journal/, Daily/, Inbox/,
       Infrastructure/Loose Ends.md, Notepad). Emits candidates/<date>.md with the quoted
       line per candidate. Vault is the only input; no WebSearch in LOOK.
PICK   pick.py: if state/current exists → BUILD. Else one `claude -p` turn over the
       candidate file with GATE.md; output judge.yaml + PLAN.md or "none".
BUILD  `claude -p --resume <session>` in state/current/, prompt = "read PROJECT.md,
       do next:, update next:". Wall budget per pass (default 3 h night, 1 h day).
       PROJECT.md `next:` is the only memory across passes.
JUDGE  judge.py runs every pass; acts only at day ≥7 after `milestone_at`.
```
Session resume keeps the 96 s cold cost per project, not per turn.

## Self-improvement (tier 1) is a project, not a subsystem
Candidate "harness" = one proposed change to loop/CLAUDE.md, hooks, tool list or prompts.
Milestone = the change applied on a branch + `bench/run.py --driver claude-code` re-run.
Judge = bench delta vs docs/bench-baseline.md per GATE.md thresholds. Reverts otherwise.

## Decisions taken by the build session 2026-09-08 (cheap to reverse)
- Day lane stays on the P100 pair. Idle P100s are a bug; a bad day project is deleted by
  the judge, so the cost of a wrong pick is bounded.
- No WebSearch in LOOK. Allowed in BUILD.
- Cadence: one project at a time; LOOK once per pass; judge at 7 days from milestone.
- Bench during the day runs on :11466 with v1 worker STOPPED for the window (restart after).
