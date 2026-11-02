#!/usr/bin/env bash
# Instala Konkr Toolbox (zip ya compilado de release/) en Decky. Solo toca ~/homebrew/plugins/konkr-toolbox.
set -euo pipefail
D="$(cd "$(dirname "$0")/.." && pwd)"
Z=$(ls "$D"/release/konkr-toolbox-*.zip | sort -V | tail -1)
P="$HOME/homebrew/plugins"
[ -d "$P" ] || { echo "No existe $P: ¿está Decky instalado?"; exit 1; }
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
unzip -q "$Z" -d "$T"
sudo rm -rf "$P/konkr-toolbox"
sudo cp -r "$T/konkr-toolbox" "$P/konkr-toolbox"
sudo chown -R root:root "$P/konkr-toolbox"
sudo systemctl restart plugin_loader.service
echo "Instalado: $(basename "$Z"). Abre Modo Juego → menú ··· (Decky)."
