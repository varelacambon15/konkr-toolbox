#!/usr/bin/env bash
# Desinstala Konkr Tweaks. Primero quita el lanzador de las opciones de lanzamiento de tus juegos
# (si no, Steam intentaría usarlo). Steam tiene que estar cerrado.
# Uninstalls Konkr Tweaks. It first removes the launcher from your games' launch options. Steam must be closed.
case "${LANG:-}${LANGUAGE:-}" in es*|*:es*) ES=1 ;; *) ES=0 ;; esac
say() { if [ "$ES" = 1 ]; then echo "$1"; else echo "$2"; fi; }
APP="$HOME/.local/share/konkr-tweaks/app"

if [ -d "$APP/konkr_tweaks" ]; then
  (cd "$APP" && python3 -m konkr_tweaks.cli unwrap-all)
  rc=$?
  if [ $rc -ne 0 ]; then
    say "Cierra Steam (en Modo Escritorio: Steam -> Salir) y vuelve a ejecutar este desinstalador." \
        "Close Steam (in Desktop Mode: Steam -> Exit) and run this uninstaller again."
    exit 1
  fi
fi
rm -rf "$APP"
rm -f "$HOME/.local/bin/konkr-tweaks" "$HOME/.local/share/applications/konkr-tweaks.desktop"
# kt-run se deja: si algún juego aún lo tuviera en sus opciones, arranca igualmente.
update-desktop-database "$HOME/.local/share/applications" >/dev/null 2>&1 || true
say "Konkr Tweaks desinstalado. Las copias de seguridad siguen en ~/.local/share/konkr-tweaks/backups y tus ajustes en ~/.config/konkr-tweaks." \
    "Konkr Tweaks uninstalled. Backups remain in ~/.local/share/konkr-tweaks/backups and settings in ~/.config/konkr-tweaks."
