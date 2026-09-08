#!/usr/bin/env bash
# loop/install.sh — install the AUTOGOD v2 systemd --user units on THIS
# machine. Does not run itself as part of the build; run by hand later:
#   ./loop/install.sh              # default: lookpick only (build-order step 2)
#   ./loop/install.sh lookpick     # same, explicit
#   ./loop/install.sh full         # day + night build timers (build-order step 3+)
set -euo pipefail

MODE="${1:-lookpick}"
case "$MODE" in
    lookpick|full) ;;
    *)
        echo "usage: install.sh [lookpick|full]" >&2
        exit 2
        ;;
esac

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYSTEMD_SRC="$HERE/systemd"
UNIT_DIR="$HOME/.config/systemd/user"

mkdir -p "$UNIT_DIR"

# The .service files are always installed (a timer only ever wants the unit
# it names), but which .timer gets enabled depends on the mode.
for f in autogod-v2.service autogod-v2-night.service autogod-v2-lookpick.service \
         autogod-v2-day.timer autogod-v2-night.timer autogod-v2-lookpick.timer; do
    cp "$SYSTEMD_SRC/$f" "$UNIT_DIR/$f"
    echo "installed $UNIT_DIR/$f"
done

systemctl --user daemon-reload

if [ "$MODE" = "lookpick" ]; then
    systemctl --user disable --now autogod-v2-day.timer 2>/dev/null || true
    systemctl --user disable --now autogod-v2-night.timer 2>/dev/null || true
    systemctl --user enable --now autogod-v2-lookpick.timer
    echo "mode: lookpick — look+gate only, daily 12:30, no build"
else
    systemctl --user disable --now autogod-v2-lookpick.timer 2>/dev/null || true
    systemctl --user enable --now autogod-v2-day.timer
    systemctl --user enable --now autogod-v2-night.timer
    echo "mode: full — day (13:00) + night (23:30) build timers"
fi

echo "done. check: systemctl --user list-timers | grep autogod-v2"
