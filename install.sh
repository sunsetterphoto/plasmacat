#!/usr/bin/env bash
# PlasmaCat installer — no root needed, everything goes to ~/.local.
#
#   ./install.sh          install the newest release to ~/.local/share/plasmacat/app
#                         and keep it updated (daily systemd user timer)
#   ./install.sh --dev    use THIS checkout instead (no auto-update timer)
#
# Safe to run again: it updates an existing install in place.
set -euo pipefail

REPO="${PLASMACAT_REPO:-https://github.com/sunsetterphoto/plasmacat.git}"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
APP="$DATA/plasmacat/app"
UNITS="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
STATE="${XDG_STATE_HOME:-$HOME/.local/state}/plasmacat"
HERE="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
DEV=0
[ "${1:-}" = "--dev" ] && DEV=1

say() { printf '\033[1m==>\033[0m %s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -ne 0 ] || die "do not run this as root — PlasmaCat installs per user"
[ "${XDG_SESSION_TYPE:-}" = "wayland" ] || say "warning: PlasmaCat needs a Plasma Wayland session"
command -v git >/dev/null || die "git is required"
if ! python3 -c "import PySide6.QtDBus, PySide6.QtMultimedia" 2>/dev/null; then
  die "PySide6 is missing. On Fedora: sudo dnf install python3-pyside6
       (other distros: your python3-pyside6 package, or pip install PySide6)"
fi

mkdir -p "$DATA/plasmacat" "$STATE"
if [ "$DEV" -eq 1 ]; then
  say "Linking this checkout ($HERE) as the app"
  [ -e "$APP" ] && [ ! -L "$APP" ] && die "$APP is a real install — run ./uninstall.sh first"
  ln -sfn "$HERE" "$APP"
else
  if [ -L "$APP" ]; then rm "$APP"; fi
  if [ -d "$APP/.git" ]; then
    say "Updating the existing install"
  else
    say "Downloading PlasmaCat"
    git clone --quiet "$REPO" "$APP"
  fi
  git -C "$APP" fetch --quiet --tags origin
  LATEST="$(git -C "$APP" tag --list 'v*' --sort=-v:refname | head -n1)"
  if [ -n "$LATEST" ]; then
    say "Installing release $LATEST"
    git -C "$APP" checkout --quiet -B main "$LATEST"
  fi
fi

say "Adding the app launcher and icons"
mkdir -p "$DATA/applications"
sed "s|^Exec=.*|Exec=$APP/run.sh|" "$APP/src/plasmacat/data/plasmacat.desktop" \
  > "$DATA/applications/plasmacat.desktop"
for s in 256 128 64 48 32 22 16; do
  install -Dm644 "$APP/src/plasmacat/data/icons/plasmacat-$s.png" \
    "$DATA/icons/hicolor/${s}x${s}/apps/plasmacat.png"
done
command -v update-desktop-database >/dev/null && update-desktop-database "$DATA/applications" || true
command -v kbuildsycoca6 >/dev/null && kbuildsycoca6 >/dev/null 2>&1 || true
# an autostart entry from an older install must point at the stable path too
AUTO="${XDG_CONFIG_HOME:-$HOME/.config}/autostart/plasmacat.desktop"
[ -f "$AUTO" ] && sed -i "s|^Exec=.*|Exec=$APP/run.sh|" "$AUTO"

if [ "$DEV" -eq 0 ] && [ -z "${PLASMACAT_SANDBOX:-}" ]; then
  say "Enabling daily updates (systemd user timer)"
  mkdir -p "$UNITS"
  install -m644 "$APP/packaging/plasmacat-update.service" "$UNITS/"
  install -m644 "$APP/packaging/plasmacat-update.timer" "$UNITS/"
  systemctl --user daemon-reload
  systemctl --user enable --now plasmacat-update.timer >/dev/null
fi

say "Done. Start PlasmaCat from your app menu (or run $APP/run.sh)."
