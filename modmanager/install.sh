#!/usr/bin/env bash
# Instalador de Konkr Mod Manager (solo para tu usuario; no toca el sistema ni pide sudo).
# Installer for Konkr Mod Manager (only your user; no sudo, no system changes).
# Opción / option: --sin-servicio | --no-service  -> sin servicio en segundo plano para la app del móvil.
set -e
case "${LANG:-}${LANGUAGE:-}" in es*|*:es*) ES=1 ;; *) ES=0 ;; esac
say() { if [ "$ES" = 1 ]; then echo "$1"; else echo "$2"; fi; }
NO_SERVICE=0
for a in "$@"; do case "$a" in --sin-servicio|--no-service) NO_SERVICE=1 ;; esac; done
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP="$HOME/.local/share/konkr-modmanager/app"
BIN="$HOME/.local/bin"
DESK="$HOME/.local/share/applications"
UNIT_DIR="$HOME/.config/systemd/user"
UNIT="konkr-modmanager-server.service"

say "== Konkr Mod Manager: instalando en $APP" "== Konkr Mod Manager: installing to $APP"

if ! python3 -c "import gi; gi.require_version('Gtk','3.0'); from gi.repository import Gtk" 2>/dev/null; then
  say "AVISO: falta Python con GTK3 (python-gobject): la ventana no abrirá, pero la app del móvil sí funcionará." "WARNING: Python with GTK3 (python-gobject) is missing: the window won't open, but the phone app will work."
fi

found=""
for t in 7z 7zz unar bsdtar; do command -v "$t" >/dev/null 2>&1 && found="$found $t"; done
if [ -z "$found" ]; then
  say "AVISO: no encuentro 7z/unar/bsdtar. Solo podrás instalar mods en .zip." "WARNING: 7z/unar/bsdtar not found. Only .zip mods can be installed."
else
  say "   descompresores disponibles:$found" "   extractors available:$found"
fi

# si el servicio ya estaba funcionando, se para mientras se copian los archivos
systemctl --user stop "$UNIT" >/dev/null 2>&1 || true

mkdir -p "$APP" "$BIN" "$DESK"
rm -rf "$APP/konkr_mm"
cp -r "$SRC/konkr_mm" "$APP/"
find "$APP" -name "__pycache__" -type d -prune -exec rm -rf {} +

cat > "$BIN/konkr-modmanager" <<LAUNCHER
#!/usr/bin/env bash
cd "$APP" && exec python3 -m konkr_mm "\$@"
LAUNCHER
chmod +x "$BIN/konkr-modmanager"

cat > "$DESK/konkr-modmanager.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Konkr Mod Manager
Comment=Mods para Skyrim SE, Fallout 4 y Oblivion
Exec=$BIN/konkr-modmanager %u
Icon=applications-games
Terminal=false
Categories=Game;Utility;
MimeType=x-scheme-handler/nxm;
DESKTOP

# Servicio en segundo plano para la app del móvil: funciona aunque la ventana esté cerrada,
# también mientras usas la consola en Modo Juego.
if [ "$NO_SERVICE" = 0 ] && command -v systemctl >/dev/null 2>&1; then
  mkdir -p "$UNIT_DIR"
  cat > "$UNIT_DIR/$UNIT" <<SERVICE
[Unit]
Description=Konkr Mod Manager - servidor para la app del movil
After=network-online.target

[Service]
WorkingDirectory=$APP
ExecStart=/usr/bin/env python3 -m konkr_mm --server
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
SERVICE
  systemctl --user daemon-reload >/dev/null 2>&1 || true
  if systemctl --user enable --now "$UNIT" >/dev/null 2>&1; then
    say "   servicio para la app del móvil activado (puerto 8765)" "   phone app service enabled (port 8765)"
  else
    say "   AVISO: no se pudo activar el servicio; la app del móvil funcionará con la ventana abierta." "   WARNING: couldn't enable the service; the phone app will work while the window is open."
  fi
fi

update-desktop-database "$DESK" >/dev/null 2>&1 || true
# Enlaces nxm:// (botón "Mod Manager Download" de la web de Nexus) -> este gestor
xdg-mime default konkr-modmanager.desktop x-scheme-handler/nxm >/dev/null 2>&1 || true

echo
say "Listo. Lo tienes en el menú de aplicaciones como «Konkr Mod Manager»." "Done. It's in the application menu as \"Konkr Mod Manager\"."
say "Para usarlo en Modo Juego: clic derecho sobre él en el menú -> «Añadir a Steam»." "For Game Mode: right-click it in the menu -> \"Add to Steam\"."
say "App del móvil: abre el gestor -> pestaña «Móvil» y escanea el código QR." "Phone app: open the manager -> \"Phone\" tab and scan the QR code."
