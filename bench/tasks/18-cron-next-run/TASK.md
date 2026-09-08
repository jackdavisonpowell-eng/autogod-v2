# Task: cron next-run calculator

Right now is 2026-09-08T10:15:00. `schedule.txt` has one cron-style line
per entry, format `MIN HOUR * * *` (only minute and hour are used; the
other three fields are always `*` and can be ignored). Write `run.sh` that
prints, for each line in order, the next time (today if the time hasn't
happened yet today, else tomorrow) that schedule fires, as
`YYYY-MM-DDTHH:MM:00`, one per line, to stdout.
