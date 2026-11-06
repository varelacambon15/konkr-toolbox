# Konkr Tweaks

Per-game optimisations for Steam on SteamOS handhelds. It finds your installed games and, with one button, applies what's recommended for your device: launch settings plus a graphics profile tuned for modest hardware.

Built for the **KONKR Pocket FIT** (Snapdragon 8 Gen 3, 8 GB) running the [SteamOS ARM port](https://github.com/hashtagbasit/SteamOS-ARM-Handhelds). It also works on x86 (Steam Deck, etc.): only the FEX translator options are skipped.

> 🇪🇸 Español: [LEEME.md](LEEME.md)

## What it does

Every game has five **modes**. A mode combines the profile's graphics, internal resolution, FEX translator and fps cap:

| Mode | Graphics | Resolution | FEX | FPS cap |
|---|---|---|---|---|
| Max performance | Lowest | 960 × 540 | fastest | no |
| Performance | Lowest | 1280 × 720 | fast | no |
| Balanced | Medium | 1280 × 720 | fast | no |
| Quality | High | 1920 × 1080 | fast | no |
| Battery | Lowest | 1280 × 720 | fast | 30 fps |

- **“Optimise for this device”** applies the mode recommended for your CPU and RAM. On the Konkr Pocket FIT that's Performance.
- If Max performance crashes a game, use Performance: `fastest` trades stability for a little more speed.
- All modes enable NTSync and the game's own arguments (skip intros, better renderer, no anti-cheat that doesn't work on Linux…).
- Battery mode's 30 fps cap is set inside the game when the profile supports it (Black Ops III, Garry's Mod, BeamNG, Incursion Red River). Other games use the DXVK/VKD3D limiter (DirectX 9 to 12).
- In games without a profile, the mode only changes launch settings.
- A **backup of the original file** is kept: “Restore original” puts it back.

You can also turn on these **launch options** by hand for any Steam game. Modes don't change them (except the
fps limit) and they apply the next time you start the game:

| Option | What it does |
|---|---|
| **Performance** | |
| FEX translator | fast, fastest or compat |
| FPS limit | 30, 40, 45 or 60 fps (`DXVK_FRAME_RATE`, `VKD3D_FRAME_RATE`) |
| Turn off the game's vsync | Avoids sudden drops from 60 to 30 fps (`DXVK_CONFIG`: `dxgi.syncInterval`, `d3d9.presentInterval`) |
| Fast cores only | The game doesn't use the low-power cores (on Snapdragon 8 Gen 3, the two Cortex-A520) |
| Large shader cache | `MESA_SHADER_CACHE_MAX_SIZE=4G` |
| Lower input lag | `DXVK_CONFIG`: `maxFrameLatency = 1` |
| Force graphics API | `-dx11`, `-dx12` (Unreal), `-force-vulkan` or `-force-d3d11` (Unity) argument |
| **Stability** | |
| NTSync | `PROTON_USE_NTSYNC=1` |
| Compatible sync | `PROTON_NO_ESYNC=1 PROTON_NO_FSYNC=1`, no NTSync |
| Random crash fix | `PROTON_HEAP_DELAY_FREE=1` |
| Use WineD3D instead of DXVK | `PROTON_USE_WINED3D=1` |
| Load mod DLLs | `WINEDLLOVERRIDES=dinput8,winmm,version=n,b` |
| **Extras and diagnostics** | |
| Steam Deck mode, MangoHud, FPS counter (DXVK) | `SteamDeck=1`, `MANGOHUD=1`, `DXVK_HUD=fps` |
| No DXVK/VKD3D logs | `DXVK_LOG_LEVEL=none`, `VKD3D_DEBUG=none` |
| Proton log | `PROTON_LOG=1` (`~/steam-<appid>.log`) |

You can add your own arguments and environment variables too. The last launch is written to
`~/.local/state/konkr-tweaks/last-launch.txt`. Options can also be changed from the Konkr Toolbox plugin in Game
Mode.

“Default settings” apply to every game that has no settings of its own.

**Included profiles**

| Game | What it changes |
|---|---|
| Skyrim Special Edition | SkyrimPrefs.ini: shadows, grass, LOD, water, TAA/FXAA, resolution |
| Fallout 4 | Fallout4Prefs.ini: shadows, god rays, SSR, LOD, resolution (V-sync untouched) |
| Oblivion | Oblivion.ini: grass, actor shadows, water reflections, resolution |
| 7 Days to Die *(experimental)* | Graphics options in the Wine registry; D3D11, no EAC, no intro; resolution |
| Dying Light | video.scr: textures, view distance, shadows, grass, resolution; `-nologos`; write protection |
| GTA V (Legacy) | settings.xml: all quality and density options, resolution; `-ignoreDifferentVideoCard` |
| Call of Duty: Black Ops III | players/config.ini: fps, resolution scale, textures, shadows, AA…; write protection |
| BeamNG.drive *(experimental)* | game-settings.ini: post-processing and fps limit; starts with Vulkan |
| Garry's Mod | autoexec.cfg with multicore rendering and light effects; `-novid`, resolution |
| Incursion Red River *(experimental)* | GameUserSettings.ini and Engine.ini: no Lumen or virtual shadows, 1 GB texture pool, scalability, resolution, fps limit |
| Unreal Engine 4/5 games *(generic, experimental)* | Engine.ini [SystemSettings] and resolution |

## How launching works

Launch settings go through a tiny launcher. It's added once to each game's launch options:
```
~/.local/bin/kt-run %command%
```
The app does it for you: the **Enable** button on a game, or **Enable in all games**. Existing options are kept, and `konkr-game fast %command%` is converted automatically.

Steam saves launch options when it exits, so to write them the app closes Steam briefly and reopens it. This only works in **Desktop Mode**. In Game Mode there's a button to copy the text instead.

If the app is uninstalled or anything fails, the launcher starts the game unchanged: it never prevents you from playing.

## Install

```bash
git clone https://github.com/<you>/konkr-tweaks.git
bash konkr-tweaks/install.sh
```
Then open **Konkr Tweaks** from the menu in Desktop Mode.

Uninstall (with Steam closed): `bash konkr-tweaks/uninstall.sh`. It removes the launcher from your games first.

## Before optimising a game

Launch it once from Steam and close it, so it creates its configuration file. The app tells you if it's missing.

## Adding profiles

Each profile is a JSON file in `konkr_tweaks/profiles/`, or in `~/.config/konkr-tweaks/profiles/` for your own. The format is documented at the top of `konkr_tweaks/profiles.py`, and the bundled profiles are working examples.

Supported formats:
- `ini`
- `xml` (`value` attributes)
- `call` (`Command(args)`)
- `kv` (`Key = "value"`)
- `cfg` (Source)
- `reg` (Wine registry, existing values only)
- `lines`

Pull requests with new games are welcome. Please list your sources (PCGamingWiki, official docs…).

## Translations

Spanish and English. To add a language: copy `konkr_tweaks/locale/en.json` to `<code>.json` and translate the values. Check with `python3 tools/i18n_check.py`.

## Limitations

- Profiles marked experimental use values that aren't officially documented. They can be undone with “Restore original”.
- In Game Mode, launchers can't be enabled automatically. Everything else works there.
- Some games rewrite their config when you change options in their menu. Where needed there's a **Protect the file** option.

## License

MIT. Not affiliated with KONKR, Valve or any of the game studios.
