# Konkr Tweaks

Optimizaciones por juego para Steam en consolas portátiles con SteamOS. Detecta los juegos instalados y, con un botón, aplica lo recomendado para tu equipo: ajustes de arranque y un perfil gráfico pensado para hardware modesto.

Hecho para la **KONKR Pocket FIT** (Snapdragon 8 Gen 3, 8 GB) con el [port de SteamOS ARM](https://github.com/hashtagbasit/SteamOS-ARM-Handhelds). En un PC x86 (Steam Deck, etc.) también funciona: solo se omite lo que es del traductor FEX.

> 🇬🇧 English: [README.md](README.md)

## Qué hace

Cada juego tiene cinco **modos**. Un modo junta los gráficos del perfil, la resolución interna, el traductor FEX y el límite de fps:

| Modo | Gráficos | Resolución | FEX | Límite de fps |
|---|---|---|---|---|
| Máximo rendimiento | Mínimo | 960 × 540 | fastest | no |
| Rendimiento | Mínimo | 1280 × 720 | fast | no |
| Equilibrado | Medio | 1280 × 720 | fast | no |
| Calidad | Alto | 1920 × 1080 | fast | no |
| Batería | Mínimo | 1280 × 720 | fast | 30 fps |

- **«Optimizar para este equipo»** aplica el modo recomendado según CPU y RAM. En la Konkr Pocket FIT es Rendimiento.
- Si «Máximo rendimiento» cierra un juego, usa Rendimiento: `fastest` arriesga estabilidad a cambio de algo más de velocidad.
- Todos los modos activan NTSync y los argumentos propios del juego (saltar vídeos, renderizador más adecuado, sin anticheat que no funciona en Linux…).
- El límite de 30 fps del modo Batería se pone dentro del juego cuando el perfil lo permite (Black Ops III, Garry's Mod, BeamNG, Incursion Red River). En el resto se usa el limitador de DXVK/VKD3D (DirectX 9 a 12).
- En juegos sin perfil, el modo cambia solo los ajustes de arranque.
- Se guarda una **copia del archivo original**: «Restaurar original» lo deja como estaba.

Además puedes activar a mano, en cualquier juego de Steam, estas **opciones de lanzamiento**. Un modo no las
cambia (salvo el límite de fps) y se aplican la próxima vez que abras el juego:

| Opción | Qué hace |
|---|---|
| **Rendimiento** | |
| Traductor FEX | fast, fastest o compat |
| Límite de fps | 30, 40, 45 o 60 fps (`DXVK_FRAME_RATE`, `VKD3D_FRAME_RATE`) |
| Quitar el vsync del juego | Evita caídas de golpe de 60 a 30 fps (`DXVK_CONFIG`: `dxgi.syncInterval`, `d3d9.presentInterval`) |
| Solo núcleos rápidos | El juego no usa los núcleos de bajo consumo (en el Snapdragon 8 Gen 3, los dos Cortex-A520) |
| Caché de shaders grande | `MESA_SHADER_CACHE_MAX_SIZE=4G` |
| Menos retraso de los controles | `DXVK_CONFIG`: `maxFrameLatency = 1` |
| Forzar API gráfica | Argumento `-dx11`, `-dx12` (Unreal), `-force-vulkan` o `-force-d3d11` (Unity) |
| **Estabilidad** | |
| NTSync | `PROTON_USE_NTSYNC=1` |
| Sincronización compatible | `PROTON_NO_ESYNC=1 PROTON_NO_FSYNC=1`, sin NTSync |
| Arreglo de cierres aleatorios | `PROTON_HEAP_DELAY_FREE=1` |
| Usar WineD3D en vez de DXVK | `PROTON_USE_WINED3D=1` |
| Cargar DLL de mods | `WINEDLLOVERRIDES=dinput8,winmm,version=n,b` |
| **Extras y diagnóstico** | |
| Modo Steam Deck, MangoHud, contador de fps (DXVK) | `SteamDeck=1`, `MANGOHUD=1`, `DXVK_HUD=fps` |
| Sin registros de DXVK/VKD3D | `DXVK_LOG_LEVEL=none`, `VKD3D_DEBUG=none` |
| Registro de Proton | `PROTON_LOG=1` (`~/steam-<appid>.log`) |

También puedes poner argumentos y variables de entorno propios. Lo último que se lanzó queda en
`~/.local/state/konkr-tweaks/last-launch.txt`. Las opciones también se cambian desde el plugin Konkr Toolbox,
en Modo Juego.

Los «Ajustes por defecto» valen para todos los juegos que no tengan ajustes propios.

**Perfiles incluidos**

| Juego | Qué toca |
|---|---|
| Skyrim Special Edition | SkyrimPrefs.ini: sombras, hierba, LOD, agua, TAA/FXAA, resolución |
| Fallout 4 | Fallout4Prefs.ini: sombras, rayos volumétricos, SSR, LOD, resolución (no toca la sincronización vertical) |
| Oblivion | Oblivion.ini: hierba, sombras de personajes, reflejos del agua, resolución |
| 7 Days to Die *(experimental)* | Opciones gráficas del registro de Wine; arranque D3D11 sin EAC, sin intro; resolución |
| Dying Light | video.scr: texturas, distancia de visión, sombras, hierba, resolución; `-nologos`; protección contra sobrescritura |
| GTA V (Legacy) | settings.xml: todas las calidades y densidades, resolución; `-ignoreDifferentVideoCard` |
| Call of Duty: Black Ops III | players/config.ini: fps, escala de resolución, texturas, sombras, AA…; protección |
| BeamNG.drive *(experimental)* | game-settings.ini: posprocesado y límite de fps; arranque con Vulkan |
| Garry's Mod | autoexec.cfg con renderizado multinúcleo y efectos ligeros; `-novid`, resolución |
| Incursion Red River *(experimental)* | GameUserSettings.ini y Engine.ini: sin Lumen ni sombras virtuales, 1 GB para texturas, calidades, resolución, límite de fps |
| Juegos Unreal Engine 4/5 *(genérico, experimental)* | Engine.ini [SystemSettings] y resolución |

## Cómo funciona el arranque

Los ajustes de arranque se aplican mediante un pequeño lanzador. Se añade una sola vez a las opciones de lanzamiento de cada juego:
```
~/.local/bin/kt-run %command%
```
El programa lo pone por ti: botón **Activar** en un juego, o **Activar en todos los juegos**. Las opciones que ya tuvieras se conservan, y si tenías `konkr-game fast %command%` se convierte automáticamente.

Steam guarda esas opciones al cerrarse, así que para escribirlas el programa cierra Steam un momento y lo vuelve a abrir. Esto solo se puede hacer en **Modo Escritorio**. En Modo Juego tienes el botón de copiar el texto.

Si desinstalas el programa o algo falla, el lanzador arranca el juego tal cual: nunca impide jugar.

## Instalar

```bash
git clone https://github.com/<tu-usuario>/konkr-tweaks.git
bash konkr-tweaks/install.sh
```
Después, en Modo Escritorio, abre **Konkr Tweaks** desde el menú.

Desinstalar (con Steam cerrado): `bash konkr-tweaks/uninstall.sh`. Primero quita el lanzador de tus juegos.

## Antes de optimizar un juego

Ábrelo una vez desde Steam y ciérralo: así crea su archivo de configuración. El programa te avisa si falta.

## Añadir perfiles

Cada perfil es un JSON en `konkr_tweaks/profiles/`, o en `~/.config/konkr-tweaks/profiles/` para los tuyos. La documentación del formato está al principio de `konkr_tweaks/profiles.py`, y los perfiles incluidos sirven de ejemplo.

Formatos soportados:
- `ini`
- `xml` (atributos `value`)
- `call` (`Comando(args)`)
- `kv` (`Clave = "valor"`)
- `cfg` (Source)
- `reg` (registro de Wine, solo valores que existan)
- `lines`

## Traducciones

Español e inglés. Para añadir un idioma: copia `konkr_tweaks/locale/en.json` a `<código>.json` y traduce los valores. Comprueba con `python3 tools/i18n_check.py`.

## Limitaciones

- Los perfiles marcados como experimentales usan valores que no están documentados oficialmente. Se pueden deshacer con «Restaurar original».
- En Modo Juego no se pueden activar los lanzadores automáticamente. Lo demás sí funciona.
- Algunos juegos rehacen su configuración al cambiar opciones en su menú. En los que lo necesitan existe la opción **Proteger el archivo**.

## Licencia

MIT. No está afiliado a KONKR, Valve ni a ninguno de los estudios de los juegos.
