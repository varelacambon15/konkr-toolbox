#!/usr/bin/env bash
# Instalador de Konkr Tweaks (solo para tu usuario; no pide sudo ni toca el sistema).
# Installer for Konkr Tweaks (your user only; no sudo, no system changes).
set -e
case "${LANG:-}${LANGUAGE:-}" in es*|*:es*) ES=1 ;; *) ES=0 ;; esac
say() { if [ "$ES" = 1 ]; then echo "$1"; else echo "$2"; fi; }
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP="$HOME/.local/share/konkr-tweaks/app"
BIN="$HOME/.local/bin"
DESK="$HOME/.local/share/applications"

say "== Konkr Tweaks: instalando en $APP" "== Konkr Tweaks: installing to $APP"
if ! python3 -c "import gi; gi.require_version('Gtk','3.0'); from gi.repository import Gtk" 2>/dev/null; then
  say "AVISO: falta Python con GTK3 (python-gobject): la ventana no abrirá, pero el plugin de Decky y el lanzador sí funcionan." "WARNING: Python with GTK3 (python-gobject) is missing: the window won't open, but the Decky plugin and the launcher still work."
fi

mkdir -p "$APP" "$BIN" "$DESK"
rm -rf "$APP/konkr_tweaks"
cp -r "$SRC/konkr_tweaks" "$APP/"
find "$APP" -name "__pycache__" -type d -prune -exec rm -rf {} +

# Lanzador que Steam ejecuta delante de cada juego: ~/.local/bin/kt-run %command%
# Si el programa no está, arranca el juego tal cual (nunca impide jugar).
cat > "$BIN/kt-run" <<'KTRUN'
#!/bin/sh
APP="$HOME/.local/share/konkr-tweaks/app"
if [ -d "$APP/konkr_tweaks" ] && command -v python3 >/dev/null 2>&1; then
  exec python3 -c "import sys; sys.path.insert(0, sys.argv.pop(1)); from konkr_tweaks.kt_run import main; main()" "$APP" "$@"
fi
exec "$@"
KTRUN
chmod +x "$BIN/kt-run"

cat > "$BIN/konkr-tweaks" <<LAUNCHER
#!/usr/bin/env bash
cd "$APP" && exec python3 -m konkr_tweaks "\$@"
LAUNCHER
chmod +x "$BIN/konkr-tweaks"

cat > "$DESK/konkr-tweaks.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Konkr Tweaks
Comment=Optimizaciones por juego / Per-game optimisations
Exec=$BIN/konkr-tweaks
Icon=preferences-system-performance
Terminal=false
Categories=Game;Utility;Settings;
DESKTOP
update-desktop-database "$DESK" >/dev/null 2>&1 || true

echo
say "Listo. Lo tienes en el menú de aplicaciones como «Konkr Tweaks»." "Done. It's in the application menu as \"Konkr Tweaks\"."
say "Ábrelo en Modo Escritorio la primera vez para activar el lanzador en tus juegos." "Open it in Desktop Mode the first time to enable the launcher in your games."
