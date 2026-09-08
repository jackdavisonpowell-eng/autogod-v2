# Task: rotate logs

Write `run.sh` that rotates logs in `./logs` when run once with no
arguments: `app.log.2` -> `app.log.3` (overwriting/dropping whatever was
there), `app.log.1` -> `app.log.2`, `app.log` -> `app.log.1`, then create a
new empty `app.log`. Preserve file contents exactly through the moves.
