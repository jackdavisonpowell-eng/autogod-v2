# dsh (DeepSeek Harness) on thebeast — install + headless smoke notes

2026-09-08. All work done over `ssh thebeast` (user `jack`, no sudo/root used
anywhere). Config files here (`env.sh`, `settings.yaml`) are copies of what
was actually installed on thebeast.

## Versions

- thebeast system node: v18.20.4 (too old, `dsh` requires Node >=22.19 — left
  untouched, never used).
- nvm: v0.40.1, installed to `~/.nvm` (no root needed).
- node via nvm: v22.23.2 (npm 10.9.8), `nvm alias default -> 22`.
- `dsh`: `@deepseek-ai/dsh@0.1.2-rc.1`, installed with
  `npm i -g @deepseek-ai/dsh` under the nvm node 22 environment.
  Binary: `~/.nvm/versions/node/v22.23.2/bin/dsh`.
- Brain: llama.cpp OpenAI-compatible server at `http://127.0.0.1:11466/v1`,
  model id `autogod` (Q4_K_M, 27.3B params, n_ctx 98304), no auth. GPUs were
  ~97% busy from other load during this whole session (~12 tok/s effective).

## Provider wiring

`dsh` has no generic "point at an OpenAI-compatible endpoint" CLI flag — it's
settings-driven. The adapter that supports arbitrary OpenAI-compatible
gateways is `@deepseek-ai/dsh-llm-pi-ai` (plugin id `llm-pi-ai`), configured
via the `llm-pi-ai:` section of `~/.dsh/settings.yaml` (YAML/JSON, hot-reloaded,
no restart needed). A route not in pi-ai's built-in catalog needs `api`,
`baseURL`, and a non-empty `models` list. `api: openai-completions` is a real,
documented value (see `dsh-llm-pi-ai` README example under "Acme Gateway").

pi-ai's OpenAI-compatible client insists on *some* API key being present even
for an unauthenticated local server, so `apiKeyEnv: DSH_LOCAL_API_KEY` points
at an env var set to a throwaway placeholder value (see `env.sh`).

The process-wide default model for fresh agents (used by `dsh --profile
headless` since it always starts a fresh agent) is set via the
`agent-default-model:` settings section (plugin id `agent-default-model`),
pointing at `provider: autogod, model: autogod`. Composition default before
this override was `deepseek-official` / `deepseek-v4-flash` (cloud, would
need a DeepSeek API key — not used).

Full file installed at `~/.dsh/settings.yaml` on thebeast — copy in
`bench/dsh/settings.yaml`.

## Confirmed flags (from `dsh --help`, `dsh --profile headless --help`,
`dsh --profile headless --dump-config`, and the `@deepseek-ai/dsh-headless`
package README under `~/.nvm/versions/node/v22.23.2/lib/node_modules/
@deepseek-ai/dsh/node_modules/@deepseek-ai/dsh-headless/README.md`)

| Need | Status | Detail |
|---|---|---|
| headless / non-interactive run | **CONFIRMED** | `dsh --profile headless "<task text>"`. One task per invocation, prints reasoning to stderr, final assistant text to stdout, exits. Exit code 0 = task completed with a final turn, 1 = aborted/errored/no-turn. |
| tool allowlist | **not found as a flag** | No `--tools`/`--allow` flag on `dsh` or the headless profile. Sandbox behavior is controlled by env var `DSH_PERMISSION_MODE` (`read-only` \| `workspace-write` [default] \| `danger-full-access`), read by the `sandbox-policy` and `approval` plugins (seen in `--dump-config`). `workspace-write` + `ask` approval is default; headless has no interactive terminal to answer an approval prompt, so in practice it ran under whatever the default preset auto-allows for file read/write in the workspace (the smoke test's file create+read worked with zero env overrides — no `DSH_PERMISSION_MODE` was set). No finer-grained per-tool allowlist surface was found. |
| working dir | **not a flag — implicit** | No `--cwd`. `sandbox-policy` config sets `workspaceRoot: process.cwd()`, i.e. the sandbox root is wherever you `cd` before invoking `dsh`. We `cd /tmp/autogod-dsh-smoke` before running. |
| max turns / max steps | **not found** | No such flag on `dsh`/headless, and no matching key in `dsh --profile headless --dump-config` (grepped for max.?steps/max.?turn — nothing). The headless README describes "one task per run" but does not expose a step/turn cap; the agent just runs to quiescence per task. |
| JSON or log output | **not found** | Headless only ever prints plain text: non-empty reasoning deltas to stderr under `dsh: reasoning:` headers, final assistant message to stdout. No `--json`/`--output` flag exists on the headless profile. |
| session resume | **not found for headless** | `--resume <session>` exists as an example for the `tui` profile (`dsh --profile tui --resume <session>`) but is **not** available under `--profile headless` (help text confirmed no such option) — the headless package README states explicitly: "Runs through the `dsh` launcher... one task per run... no interactive follow-up," i.e. resume is out of scope for this profile by design. |

## Smoke test result

Command (run from `/tmp/autogod-dsh-smoke` on thebeast, after `source
env.sh`):

```sh
cd /tmp/autogod-dsh-smoke
dsh --profile headless "Create a file hello.txt containing the word autogod, then read it back and reply DONE"
```

- Exit code: 0
- Wall time: **339 seconds** (GPUs were shared/~97% busy elsewhere, ~12 tok/s)
- stdout (final assistant message): `DONE`
- `hello.txt` contents: `autogod` — **correct**
- stderr showed three reasoning deltas (task understanding → "I'll read it
  back" → final confirmation), consistent with a `write_file` + `read_file`
  tool-call sequence executing without any approval prompt blocking it.

A prior connectivity check (`dsh --profile headless "Reply with exactly the
single word: PONG"`) took 62s and returned `PONG`, confirming the `autogod`
provider route was live before running the full file-write smoke test.

## Everything installed, nothing needed root

nvm, node 22, and the global `dsh` npm package all installed entirely under
`$HOME` (`~/.nvm`, npm global prefix under the nvm node dir). No `sudo` was
used or needed anywhere in this setup.
