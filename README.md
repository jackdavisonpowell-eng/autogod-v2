# AUTOGOD v2 — one loop, local brain

A headless coding harness (Claude Code, or DeepSeek Harness if the bench says so) driving a
local 27B model on a pair of Tesla P100s. It reads what changed in an Obsidian vault, picks
ONE candidate that passes a frozen gate (`GATE.md`), plans it, builds it over nights, and
after seven days a script — not the model — reads whether the thing was actually used.
Unused projects are deleted and written to `state/dead.md` with the reason.

- `docs/ARCHITECTURE.md` — layout, one pass, decisions
- `GATE.md` — frozen; the loop cannot edit it
- `bench/` — the frozen 20-task eval set and runner (`python3 bench/run.py --driver claude-code`)
- `proxy/` — the only glue between Claude Code and llama.cpp (`/v1/messages` system-role fold)
- `loop/` — look → pick → build → judge; `hooks/guard.py` is the hard boundary
- `judge/` — the 7-day probe reader

`make test` runs everything offline with a mock driver.
