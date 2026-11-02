# Konkr Mod Manager

A touch-friendly mod manager for **Skyrim Special Edition**, **Fallout 4** and **Oblivion** on SteamOS handhelds, with a **phone companion app** to browse Nexus Mods and send mods to the console from your phone.

It was built for the **KONKR Pocket FIT** running the [SteamOS ARM port](https://github.com/hashtagbasit/SteamOS-ARM-Handhelds), but nothing in it is ARM-specific: it should also work on a Steam Deck or any Linux PC that runs these games through Steam + Proton (not tested there yet).

> 🇪🇸 **¿Hablas español?** Lee [LEEME.md](LEEME.md). El programa está en español e inglés y elige el idioma del sistema automáticamente.

## Features

**On the console (GTK app, works in Desktop and Game Mode)**
- Finds the games in every Steam library (internal storage and microSD).
- Installs mods from `.zip`, `.7z` and `.rar`, or straight from Nexus Mods with your API key (direct downloads need Premium; free accounts can use the website's *Mod Manager Download* button / `nxm://` links).
- Enable, disable and reorder mods. Nothing touches the game folder until you press **Apply**.
- Plugin load order (`plugins.txt` inside the Proton prefix). Creations installed from the game's menu are kept. Oblivion's timestamp-based order is handled.
- Script extenders (SKSE64, F4SE, xOBSE): installs them to the game root and swaps the launcher so Steam's *Play* button starts them. Undo with one click.
- Fallout 4: one-click INI fix so loose files and the plugin list are used.
- Safe by design: original game files are backed up before being overwritten and restored when a mod is removed; *Remove all mods* returns the game to vanilla. Hard links are used when possible, so mods don't take twice the space.

**On your phone (web app served by the console, no install needed)**
- Browse Nexus: trending, most endorsed, most downloaded, new and updated mods.
- Search by name or author, filter by category.
- Mod page with images, description and files, and a **Send to the Konkr** button (downloads and installs on the console).
- Your mod list: enable, reorder, rename, remove, plugin order, **check for updates** and **Apply**.
- Download progress, and folder selection for mods with FOMOD installers.
- Pair once with a QR code or a 6-digit PIN. Works over your local Wi-Fi only.

## Requirements

- SteamOS (or another Linux) with Steam and the games installed through Proton.
- Python 3 with GTK 3 bindings (`python-gobject`). The SteamOS ARM port ships them.
- `7z`, `unar` or `bsdtar` to extract `.7z`/`.rar` (`.zip` always works).
- Optional: a Nexus Mods account and your **personal API key** (Nexus → Settings → API Keys).

## Install

```bash
# in Desktop Mode, in a terminal (Konsole):
git clone https://github.com/<you>/konkr-modmanager.git
bash konkr-modmanager/install.sh
```

The installer only touches your user folder (no `sudo`):
- the program goes to `~/.local/share/konkr-modmanager/app`
- a menu entry and a `konkr-modmanager` command are created
- a small user service (`konkr-modmanager-server`) is enabled so the phone app works even when the window is closed. Skip it with `bash install.sh --no-service`.

To use it in Game Mode, right-click it in the app menu → **Add to Steam**.

Uninstall with `bash konkr-modmanager/uninstall.sh` (your mods and settings are kept).

## First steps

1. Launch each game once from Steam and close it, so Proton creates its prefix (where `plugins.txt` lives).
2. Open Konkr Mod Manager, pick the game, and paste your Nexus API key in the **Nexus** tab.
3. Add mods, press **Apply to game** (with the game closed) and play.
4. For the phone app: open the **Phone** tab and scan the QR code with your phone (same Wi-Fi). Then use your browser's *Add to Home screen*.

## Known limitations

- FOMOD installers are not interpreted yet: you pick the folders to install by hand.
- No automatic LOOT-style sorting yet.
- Oblivion: BSA archive invalidation isn't set up yet, so some texture replacers may not show. Oblivion Remastered is not supported.
- Tools that only run on Windows (Nemesis, BodySlide, DynDOLOD…) are out of scope for now.
- The phone app is served over plain HTTP on your local network and protected by the pairing PIN; don't expose port 8765 to the internet.

## Translations

The interface is available in Spanish and English. Spanish texts are the keys; each language is a JSON file in `konkr_mm/locale/`. To add a language:

1. Copy `konkr_mm/locale/en.json` to `konkr_mm/locale/<code>.json` (for example `fr.json`).
2. Change `__language_name__` and translate the values. Keep the keys and anything in braces such as `{name}`.
3. Run `python3 tools/i18n_check.py` to spot missing strings or placeholders.

The same file translates the console app and the phone app.

## Nexus Mods API

The manager uses the Nexus Mods public API with each user's own API key, sending `Application-Name: KonkrModManager` and its version, as the [Nexus API acceptable use policy](https://help.nexusmods.com/article/114-api-acceptable-use-policy) requires. Your key is stored only on your device (`~/.local/share/konkr-modmanager/config.json`, readable only by your user) and is never sent anywhere except Nexus.

## License

MIT, see [LICENSE](LICENSE). Includes [QR Code generator](https://www.nayuki.io/page/qr-code-generator-library) by Project Nayuki (MIT).

Not affiliated with KONKR, Valve, Bethesda or Nexus Mods.
