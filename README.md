# Konkr Toolbox

Plugin de [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader) para la **KONKR Pocket FIT** con
[SteamOS ARM](https://github.com/hashtagbasit/SteamOS-ARM-Port). Reúne herramientas para la consola en el menú
de acceso rápido (botón `···`), sin salir del Modo Juego. Cada herramienta es una sección cerrada detrás de un
botón: solo se abre (y carga) cuando la tocas.

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

### Dependencias
- Para cuando un programa dice *«The following component(s) are required to run this program…»*.
- Eliges el juego (de Steam o añadido como «no Steam», siempre que ya tenga prefijo de Proton) y qué instalar.
- Ahora mismo: **Microsoft Visual C++ 2015-2022**, en versión **x64** (juegos de PC de 64 bits), **x86** (32 bits) o
  **arm64** (programas ARM). Descarga el instalador oficial de Microsoft (o usa el `vc_redist.<arq>.exe` que ya
  tengas en `~/Downloads`) y lo ejecuta en silencio con el mismo Proton que usa ese juego, dentro de su prefijo.
- Registro: `~/.cache/konkr-toolbox/deps.log`.
- Sin probar todavía en una Konkr real: si falla, el registro dice por qué.
- Para añadir otra dependencia: una entrada en `DEPS` de `py_modules/ktb_deps.py` y otra en `DEPS` de
  `src/DepsSection.tsx`.

### Mapeos de mando (Steam Input)
- Busca archivos `.vdf` de Steam Input en tu carpeta personal (Descargas, Documentos…) y en la tarjeta SD, por
  ejemplo los que bajas de [steaminputdb.com](https://www.steaminputdb.com) con **Download .vdf**.
- **Aplicar a este juego**: lo instala como plantilla y abre la configuración del mando del juego elegido. Ahí,
  **Explorar configuraciones → Plantillas** y eliges ese nombre. Sirve también para juegos añadidos como «no Steam».
- **Instalar como plantilla**: lo deja disponible en las plantillas de todos los juegos.
- **ID de SteamInputDB**: el número de `steaminputdb.com/config/NÚMERO`. Steam descarga ese mapeo y te deja
  aplicarlo al juego elegido, sin bajar ningún archivo.
- Las plantillas se guardan en `~/.local/share/Steam/controller_base/templates` con una copia en `~/mapeos-steam`.
  Si una actualización de Steam las borra, el plugin las vuelve a poner al arrancar.
- Quitar plantilla: borra la plantilla y su copia. Solo toca las que instaló el Toolbox (`konkr_*.vdf`).
- Sin probar todavía en una Konkr real. Si un mapeo es de otro tipo de mando, Steam suele adaptarlo, pero revísalo
  en *Editar mapeo*.

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
- **Dependencies**: installs what a game needs into its Proton prefix, using that game's own Proton. For now the
  Microsoft Visual C++ 2015-2022 redistributable (x64, x86 or arm64). Untested on real hardware yet.
- **Controller layouts**: finds Steam Input `.vdf` files (home folder and SD card, e.g. downloaded from
  steaminputdb.com) and applies them to a game, including non-Steam ones, by installing them as Steam templates and
  opening that game's controller settings. Can also apply a SteamInputDB ID directly. Templates are backed up to
  `~/mapeos-steam` and restored if a Steam update wipes them. Untested on real hardware yet.
- **SSH / SFTP**: toggle the SSH server (persistent across reboots and in Game Mode) and see status, IP
  addresses, Wi-Fi, port, user, hostname and a ready-to-use `sftp://` address. Warns if your user has no password.

Install: download the zip from Releases, enable Decky's Developer mode, then Developer → Install Plugin from ZIP.

## Licencia / License

MIT
