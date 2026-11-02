# Konkr Mod Manager

Gestor de mods táctil para **Skyrim Special Edition**, **Fallout 4** y **Oblivion** en consolas portátiles con SteamOS, con una **app para el móvil** para explorar Nexus Mods y mandar mods a la consola desde el sofá.

Está hecho para la **KONKR Pocket FIT** con el [port de SteamOS ARM](https://github.com/hashtagbasit/SteamOS-ARM-Handhelds). No usa nada específico de ARM, así que debería funcionar también en una Steam Deck o en cualquier PC con Linux que use Steam y Proton (aún sin probar).

> 🇬🇧 English: see [README.md](README.md).

## Qué hace

**En la consola (app GTK, en Modo Escritorio y Modo Juego)**
- Encuentra los juegos en todas tus bibliotecas de Steam (memoria interna y microSD).
- Instala mods desde `.zip`, `.7z` y `.rar`, o directamente desde Nexus Mods con tu clave de API. La descarga directa requiere Premium; con cuenta gratuita se usa el botón *Mod Manager Download* de la web (enlaces `nxm://`).
- Activar, desactivar y ordenar mods. Nada toca la carpeta del juego hasta que pulsas **Aplicar al juego**.
- Orden de plugins (`plugins.txt` dentro del prefijo de Proton). Respeta las Creations instaladas desde el menú del juego y el orden por fechas de Oblivion.
- Script extenders (SKSE64, F4SE, xOBSE): los instala en la raíz del juego y cambia el launcher para que el botón *Jugar* de Steam los arranque. Se deshace con un botón.
- Fallout 4: ajuste de los INI con un botón para que lea los archivos sueltos y la lista de plugins.
- Seguro: guarda una copia de los archivos originales antes de sobrescribirlos y los devuelve al quitar el mod. *Quitar todos los mods* deja el juego como de fábrica. Usa enlaces duros cuando puede, así cada mod no ocupa el doble.

**En el móvil (web que sirve la propia consola, no hay que instalar nada)**
- Explorar Nexus: tendencias, más valorados, más descargados, nuevos y actualizados.
- Buscar por nombre o por autor y filtrar por categoría.
- Ficha del mod con imagen, descripción y archivos, y botón **Enviar a la Konkr** (descarga e instala en la consola).
- Tu lista de mods: activar, ordenar, renombrar, quitar, orden de plugins, **Buscar actualizaciones** y **Aplicar**.
- Progreso de descargas, y elección de carpetas para mods con instalador FOMOD.
- Se empareja una vez con un código QR o un PIN de 6 cifras. Solo funciona en tu Wi-Fi.

## Instalar

```bash
# en Modo Escritorio, en una terminal (Konsole):
git clone https://github.com/<tu-usuario>/konkr-modmanager.git
bash konkr-modmanager/install.sh
```

No pide contraseña ni toca el sistema:
- el programa va a `~/.local/share/konkr-modmanager/app`
- se crea una entrada en el menú y el comando `konkr-modmanager`
- se activa un pequeño servicio de usuario (`konkr-modmanager-server`) para que la app del móvil funcione con la ventana cerrada. Para no instalarlo: `bash install.sh --sin-servicio`.

Para usarlo en Modo Juego: clic derecho sobre él en el menú → **Añadir a Steam**.

Para desinstalar: `bash konkr-modmanager/uninstall.sh` (tus mods y ajustes se conservan).

## Primeros pasos

1. Abre cada juego una vez desde Steam y ciérralo, para que Proton cree su prefijo (donde está `plugins.txt`).
2. Abre Konkr Mod Manager, elige el juego y pega tu clave de API de Nexus en la pestaña **Nexus** (Nexus → Settings → API Keys → *Personal API Key*).
3. Añade mods, pulsa **Aplicar al juego** (con el juego cerrado) y a jugar.
4. App del móvil: pestaña **Móvil** → escanea el QR con el móvil (misma Wi-Fi) y usa *Añadir a pantalla de inicio* en el navegador.

## Script extenders

- Descarga la versión que coincida con la de tu juego en Steam y añádela como un mod más: el programa detecta que va en la raíz. Pulsa Aplicar.
- Pestaña **Juego** → **Arrancar con SKSE64** (o F4SE/xOBSE).
- Si Steam actualiza el juego, el script extender deja de funcionar hasta que salga su versión nueva. Mientras tanto, **Restaurar launcher original**.

## Limitaciones conocidas

- Los instaladores FOMOD aún no se interpretan: eliges a mano las carpetas.
- Todavía no hay ordenación automática tipo LOOT.
- Oblivion: falta la invalidación de archivos BSA, así que algunos reemplazos de texturas pueden no verse. Oblivion Remastered no está soportado.
- Herramientas que solo funcionan en Windows (Nemesis, BodySlide, DynDOLOD…) quedan fuera por ahora.
- La app del móvil funciona por HTTP en tu red local, protegida por el PIN. No abras el puerto 8765 a internet.
- Si el móvil no conecta estando en la misma Wi-Fi, puede que la red aísle los dispositivos entre sí (pasa en algunos edificios y repetidores). Usa el punto de acceso del móvil o del portátil.

## Traducciones

El programa está en español e inglés. Los textos en español son las claves y cada idioma es un JSON en `konkr_mm/locale/`. Para añadir uno: copia `en.json` a `<código>.json`, cambia `__language_name__`, traduce los valores (sin tocar las claves ni lo que va entre llaves, como `{name}`) y comprueba con `python3 tools/i18n_check.py`. El mismo archivo traduce la app de la consola y la del móvil.

## Licencia

MIT, ver [LICENSE](LICENSE). Incluye [QR Code generator](https://www.nayuki.io/page/qr-code-generator-library) de Project Nayuki (MIT).

No está afiliado a KONKR, Valve, Bethesda ni Nexus Mods.
