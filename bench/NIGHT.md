# Night brain / GPU swap — read-only findings (2026-09-08)

How and when FRIDAY's V100 becomes the night brain at `:11467`, gathered
by reading (no writes, no `systemctl`) on thebeast: `systemctl --user
list-timers`, `systemctl list-timers`, `systemctl cat autogod-guard`,
`~/friday/services/autogod/`, `~/*.sh`, and the actual source of the swap
(`~/autogod/services/night-lane.sh`, `~/friday/friday/night.py`).

## The swap is voice-triggered, not clock-triggered

Jack tells FRIDAY he's going to bed. That calls `friday.night.enter()`
(`/home/jack/friday/friday/night.py`), which:

1. Writes `/dev/shm/friday-night.json` with `until` = the next 08:00
   (`WAKE_HOUR = 8`, hardcoded).
2. Spawns `/home/jack/autogod/services/night-job.sh start` (the V1
   worker's own day-plan/agenda job — unrelated to the GPU swap).
3. Spawns `/home/jack/autogod/services/night-lane.sh start` — **this is
   the actual card swap.**

So there is no fixed clock time the brain comes up; it depends on when
Jack goes to bed. Confirmed from `/home/jack/friday/data/night-lane.log`:
last night (2026-09-07) it started at **23:27:51 EDT**, health confirmed
on `:11467` at **23:30:28 EDT** (~2.5 min to load the 27B).

## What `night-lane.sh start` does (the actual swap)

`/home/jack/autogod/services/night-lane.sh` (uses `sudo systemctl`, which
is why bench must never touch it — it's existing infra, read-only for us):

1. Refuses if nothing is tagged `overnight` in loose-ends (unless
   `--forced`) — never takes FRIDAY's cards for an empty queue.
2. `sudo systemctl stop friday-brain friday-sight`
3. `sudo systemctl start autogod-night-brain` — launches llama-server on
   the **V100** at **:11467**, same model as day
   (`Huihui-Qwen3.8-27B-abliterated.i1-Q4_K_M.gguf`,
   `~/stack/llama.cpp-next/build-nccl/bin/llama-server`).
   Unit: `autogod-night-brain.service`, `Conflicts=friday-brain.service`.
4. Polls `:11467/health` up to 180s; on failure rolls back
   (`give_cards_back`) and the night runs day-lane-only.
5. Once healthy, starts its own loose-ends worker lane (separate from our
   bench, don't touch).

## Hand-back to FRIDAY (deadline for the dsh half)

Two mechanisms, same target time:

- **Normal:** `friday.night.exit_if_over()`, polled by FRIDAY's own loop.
  Fires once `now >= until` (the 08:00 computed at bedtime) → calls
  `night-lane.sh stop` → `sudo systemctl stop autogod-night-brain` +
  `sudo systemctl start friday-sight friday-brain`.
- **Backstop:** system timer `friday-night-exit.timer`
  (`OnCalendar=*-*-* 08:05:00`, `Persistent=true`) → runs
  `friday-night-exit.service`, which force-stops the night brain and
  restores FRIDAY's services if either look wrong. Confirmed firing
  in the log today (2026-09-08) at **08:05:04 EDT**, FRIDAY back up on
  `:11460` by **08:07:15 EDT**.

**Deadline used by `bench/night.sh`: 08:00 local (WAKE_HOUR), so the dsh
half aborts at 07:40 local (08:00 minus 20 min). The hard outer bound if
something is running late is the 08:05:00 backstop — 07:40 leaves 25
minutes of margin against that, not just 20 against the nominal 08:00.**

## Confirmed by direct read (2026-09-08 16:49 EDT, no writes)

- `:11467/health` → connection refused (down, daytime, as expected).
- `:11466/health` → `{"status":"ok"}` (day brain up, shared with v1
  worker per the brief).
- `date` on thebeast: `US/Eastern (EDT, -0400)`, clock synchronized.
- No dedicated systemd timer calls `night-lane.sh start` — it is only
  ever invoked by `friday.night.enter()` (voice) or manually
  (`night-lane.sh handoff`, on-demand). `bench/night.sh` must therefore
  poll for `:11467/health`, exactly as specced — there's no fixed
  "brain up" time to sleep until.

## What bench/night.sh must NOT do (and doesn't)

Never calls `systemctl`, never touches `night-lane.sh`, `friday-brain`,
`friday-sight`, or `autogod-night-brain`. It only polls
`curl :11467/health` (read-only) and, once healthy, drives the bench
runner against the adapter proxy at `:11498` / dsh pointed directly at
`:11467`. It gives the V100 back to nobody — that's FRIDAY's own
machinery — it just has to finish and get out of the way before FRIDAY
takes it back.
