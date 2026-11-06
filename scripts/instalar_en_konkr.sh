#!/usr/bin/env bash
# Instala Konkr Toolbox (zip ya compilado de release/) en Decky. Solo toca ~/homebrew/plugins/konkr-toolbox.
set -euo pipefail
D="$(cd "$(dirname "$0")/.." && pwd)"
Z=$(ls "$D"/release/konkr-toolbox-*.zip | sort -V | tail -1)
# Konkr Tweaks (lo necesita la sección «Konkr Tweaks» del plugin). Solo tu carpeta de usuario, sin sudo.
bash "$D/tweaks/install.sh"
P="$HOME/homebrew/plugins"
[ -d "$P" ] || { echo "No existe $P: ¿está Decky instalado?"; exit 1; }
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
unzip -q "$Z" -d "$T"
sudo rm -rf "$P/konkr-toolbox"
sudo cp -r "$T/konkr-toolbox" "$P/konkr-toolbox"
sudo chown -R root:root "$P/konkr-toolbox"
sudo systemctl restart plugin_loader.service
# Acceso en el menú (Modo Escritorio) para abrir Claude Code en una terminal, si está instalado.
# Para Modo Juego: clic derecho sobre él en el menú → «Añadir a Steam» (tú decides; aquí no se toca Steam).
if [ -x "$HOME/.local/bin/claude" ]; then
  mkdir -p "$HOME/.local/share/applications"
  cat > "$HOME/.local/share/applications/claude-code.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=Claude Code
Comment=Claude Code en una terminal
Exec=konsole --workdir $HOME -e $HOME/.local/bin/claude
Icon=utilities-terminal
Terminal=false
Categories=Utility;Development;
DESK
fi
echo "Instalado: $(basename "$Z"). Abre Modo Juego → menú ··· (Decky)."
