# Contexto del proyecto (traído de una conversación anterior)

Consola: KONKR Pocket FIT (Snapdragon 8 Gen 3 / SM8650, 8 GB RAM, Adreno 750) con
SteamOS ARM de hashtagbasit (https://github.com/hashtagbasit/SteamOS-ARM-Port), v1.4
(etiqueta v1.4 comprobada en el repo). Instalada en memoria interna; juegos en microSD de 512 GB.
Usuario: steamos.

## Estado de la consola
- SSH activado y persistente (`sudo systemctl enable --now sshd`). Pendiente confirmar que
  FileZilla conecta tras reiniciar en Modo Juego.
- IP dinámica (última: 10.111.15.98). SFTP puerto 22, usuario steamos.
- Decky Loader preinstalado, corre bajo Box64. plugin_loader.service (User=root,
  HOME=/home/steamos). Plugins en ~/homebrew/plugins. El port trae "Handheld Control".
- Turnip/Mesa: no compilar salvo fallo concreto; Turnip propio solo por juego con
  VK_DRIVER_FILES.

## Programas
1. Konkr Mod Manager 0.3.1: GTK + companion web (puerto 8765), Skyrim SE / Fallout 4 /
   Oblivion, ES/EN, Nexus. NUNCA guardar la API key de Nexus.
2. Konkr Tweaks 0.3.0: optimizador por juego (GTK). install.sh → ~/.local/share/konkr-tweaks/app,
   lanzador ~/.local/bin/kt-run (`~/.local/bin/kt-run %command%`).
   - Modos: max, perf, balanced, quality, battery (optimize.py, tabla PLAN). Perfiles JSON.
   - DXVK_FRAME_RATE / VKD3D_FRAME_RATE; presets FEX fast/fastest/compat.
   - CLI JSON: `python3 -m konkr_tweaks.cli` json-games | json-status APPID |
     json-apply APPID MODO [--running] | json-restore APPID. Con --running queda "pending"
     y kt-run lo aplica al siguiente arranque (optimize.apply_pending).
3. Konkr Toolbox 0.1.0: plugin de Decky (este repo).
   - Frontend React/TS (@decky/ui, @decky/api, plantilla oficial, rollup):
     src/TweaksSection.tsx, src/SshSection.tsx, src/steam.ts, src/i18n.ts (ES/EN).
   - Backend main.py, flags ["root"]. subprocess.run vía asyncio.to_thread (Box64).
     Entorno sin LD_LIBRARY_PATH. Konkr Tweaks se ejecuta como el usuario con runuser.
   - Sección Tweaks: elegir juego (el abierto primero), ver perfil y modo, aplicar/restaurar.
     Añade kt-run con SteamClient.Apps.SetAppLaunchOptions.
   - Sección SSH: interruptor sshd; estado, IP, Wi-Fi (nmcli), puerto (sshd -T), usuario,
     hostname, sftp://. Aviso si no hay contraseña.
   - scripts/package.sh → out/konkr-toolbox-X.Y.Z.zip; .github/workflows/release.yml publica
     al subir etiqueta vX.Y.Z. MIT.
   - Instalación: Decky → Ajustes → Modo desarrollador → Desarrollador → Instalar plugin desde ZIP.
   - Probado solo con Steam simulado.

## Pendiente
- Código subido a main (commit 9bc5156). Falta probar en la consola y luego publicar la etiqueta v0.1.0.
- Instalar Konkr Tweaks 0.3.0 y el plugin en la consola y probar. Logs: ~/homebrew/logs/konkr-toolbox/.
- Ideas: monitor de temperaturas (chip 80-95 °C normal; batería < ~60 °C), copias de seguridad,
  Turnip por juego.

## Preferencias
- Verificar fuentes (releases, repos) antes de afirmar versiones.
- Tomar en serio lo que Alejandro recuerda y comprobarlo.
- Python con GUI y diálogos de archivo. Comandos listos para copiar y pegar.
