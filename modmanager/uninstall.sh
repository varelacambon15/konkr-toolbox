#!/usr/bin/env bash
# Desinstala el programa / uninstalls the program. NO borra tus mods ni toca los juegos / keeps your mods and games untouched.
# (Para dejar un juego limpio, antes usa en el programa: Juego -> «Quitar TODOS los mods del juego».)
systemctl --user disable --now konkr-modmanager-server.service >/dev/null 2>&1 || true
rm -f "$HOME/.config/systemd/user/konkr-modmanager-server.service"
systemctl --user daemon-reload >/dev/null 2>&1 || true
rm -rf "$HOME/.local/share/konkr-modmanager/app"
rm -f "$HOME/.local/bin/konkr-modmanager" "$HOME/.local/share/applications/konkr-modmanager.desktop"
update-desktop-database "$HOME/.local/share/applications" >/dev/null 2>&1 || true
case "${LANG:-}${LANGUAGE:-}" in
  es*|*:es*) echo "Programa desinstalado. Tus mods y ajustes siguen en ~/.local/share/konkr-modmanager"
             echo "(y, si el juego está en la SD, en <SD>/konkr-modmanager). Bórralos a mano si ya no los quieres." ;;
  *) echo "Program uninstalled. Your mods and settings are still in ~/.local/share/konkr-modmanager"
     echo "(and, for games on the SD card, in <SD>/konkr-modmanager). Delete them by hand if you no longer need them." ;;
esac
