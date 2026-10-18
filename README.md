# Konkr Toolbox

Plugin de [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader) para la **KONKR Pocket FIT** con
[SteamOS ARM](https://github.com/hashtagbasit/SteamOS-ARM-Port). Reúne herramientas para la consola en el menú
de acceso rápido (botón `···`), sin salir del Modo Juego.

*English below.*

## Herramientas

### Konkr Tweaks
- Elige un juego (el que está en marcha sale primero, marcado con ▶).
- Muestra si tiene perfil propio y qué modo tiene puesto.
- Aplica uno de los cinco modos: **Máximo rendimiento, Rendimiento, Equilibrado, Calidad, Batería**.
- **Restaurar original** deja los archivos del juego como estaban.
- Si el juego no tiene el lanzador `kt-run` en sus opciones de lanzamiento, lo añade sin cerrar Steam.
- Con el juego abierto, los cambios gráficos quedan pendientes y se aplican al volver a abrirlo
  (si se tocaran con el juego abierto, el juego los sobrescribiría al cerrarse).

Necesita **Konkr Tweaks 0.3.0 o posterior** instalado en
Modo Escritorio.

### Visual C++
- Para cuando un programa dice *«The following component(s) are required to run this program: Microsoft Visual C++
  2015-2022 Redistributable (arm64)»*.
- Eliges el juego (los que ya tienen prefijo de Proton) y la versión: **arm64** (programas ARM), **x64** o **x86**.
- Descarga el instalador oficial de Microsoft (o usa el `vc_redist.<arq>.exe` que ya tengas en `~/Downloads`) y lo
  ejecuta en silencio con el mismo Proton que usa ese juego, dentro de su prefijo.
- Registro: `~/.cache/konkr-toolbox/vcredist.log`.
- Sin probar todavía en una Konkr real: si falla, el registro dice por qué.

### SSH / SFTP
- Interruptor para activar o desactivar el servidor SSH (`systemctl enable/disable --now sshd`).
  Activado, sigue encendido tras reiniciar y en Modo Juego.
- Muestra estado, si arranca con la consola, IP de cada red, Wi-Fi, puerto, usuario y nombre del equipo.
- Muestra la dirección lista para FileZilla o WinSCP (`sftp://steamos@IP`).
- Avisa si tu usuario no tiene contraseña (sin ella no se puede entrar por SSH).

## Instalación

Decky ya viene instalado en SteamOS ARM para la Pocket FIT.

**Desde ZIP (recomendado)**
1. Descarga `konkr-toolbox-X.Y.Z.zip` de [Releases](../../releases).
2. Decky → ⚙ Ajustes → General → activa **Modo desarrollador**.
3. Decky → ⚙ Ajustes → **Desarrollador** → **Instalar plugin desde ZIP** y elige el archivo.
   También puedes usar **Instalar plugin desde URL** con el enlace del zip de Releases.

**Por SSH**
```sh
unzip konkr-toolbox-X.Y.Z.zip
sudo rm -rf ~/homebrew/plugins/konkr-toolbox
sudo cp -r konkr-toolbox ~/homebrew/plugins/
sudo systemctl restart plugin_loader
```

## Compilar

```sh
pnpm install
./scripts/package.sh      # crea out/konkr-toolbox-X.Y.Z.zip
```

Al subir una etiqueta `vX.Y.Z` a GitHub, el workflow `Release` compila y publica el zip automáticamente.

## Añadir otra herramienta

Cada herramienta es una sección: un componente en `src/` (frontend) y sus métodos en la clase `Plugin` de
`main.py` (backend). Se añade en `Content()` de `src/index.tsx`. Los textos están en `src/i18n.ts` (ES/EN).

## Cómo funciona

- El backend corre como root (flag `root`), necesario para activar SSH. Decky corre bajo Box64 en este port,
  así que los programas del sistema se lanzan con `subprocess` en un hilo.
- Konkr Tweaks se ejecuta siempre como tu usuario (`runuser`), con su orden `python3 -m konkr_tweaks.cli json-*`,
  para que sus ajustes y los archivos de los juegos sigan siendo tuyos.
- Las opciones de lanzamiento se cambian con `SteamClient.Apps.SetAppLaunchOptions`, que funciona con Steam abierto.
- Registro del backend: `~/homebrew/logs/konkr-toolbox/`.

---

## English

Decky plugin for the KONKR Pocket FIT on SteamOS ARM, with tools in the Quick Access Menu:

- **Konkr Tweaks**: pick a game (the running one first), see its profile and mode, apply one of five modes
  (Maximum performance, Performance, Balanced, Quality, Battery) or restore the original files. Adds the
  `kt-run` launcher to the game's launch options without closing Steam. If the game is running, graphics
  changes are applied the next time it starts. Requires Konkr Tweaks 0.3.0+.
- **Visual C++**: installs the Microsoft Visual C++ 2015-2022 redistributable (arm64, x64 or x86) into a game's
  Proton prefix, using that game's own Proton. Untested on real hardware yet.
- **SSH / SFTP**: toggle the SSH server (persistent across reboots and in Game Mode) and see status, IP
  addresses, Wi-Fi, port, user, hostname and a ready-to-use `sftp://` address. Warns if your user has no password.

Install: download the zip from Releases, enable Decky's Developer mode, then Developer → Install Plugin from ZIP.

## Licencia / License

MIT
