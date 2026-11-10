#!/usr/bin/env bash
# Remove PlasmaCat (launcher, icons, autostart, update timer, app files).
#   ./uninstall.sh           keeps your cats (save game) for a later reinstall
#   ./uninstall.sh --purge   also deletes the save game and caches
set -euo pipefail
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
CFG="${XDG_CONFIG_HOME:-$HOME/.config}"

# PLASMACAT_SANDBOX=1 (tests): never touch the live session
if [ -z "${PLASMACAT_SANDBOX:-}" ]; then
  pkill -TERM -f 'python[0-9.]* -m plasmacat\.main' 2>/dev/null || true
  systemctl --user disable --now plasmacat-update.timer >/dev/null 2>&1 || true
fi
rm -f "$CFG/systemd/user/plasmacat-update.service" "$CFG/systemd/user/plasmacat-update.timer"
[ -n "${PLASMACAT_SANDBOX:-}" ] || systemctl --user daemon-reload 2>/dev/null || true
rm -f "$DATA/applications/plasmacat.desktop" "$CFG/autostart/plasmacat.desktop"
for s in 256 128 64 48 32 22 16; do rm -f "$DATA/icons/hicolor/${s}x${s}/apps/plasmacat.png"; done
APP="$DATA/plasmacat/app"
if [ -L "$APP" ]; then rm "$APP"; else rm -rf "$APP"; fi
if [ "${1:-}" = "--purge" ]; then
  rm -rf "$DATA/plasmacat" "${XDG_CACHE_HOME:-$HOME/.cache}/plasmacat" \
         "${XDG_STATE_HOME:-$HOME/.local/state}/plasmacat"
  echo "PlasmaCat removed, including your save game."
else
  echo "PlasmaCat removed. Your cats are kept in $DATA/plasmacat/save.json."
fi
