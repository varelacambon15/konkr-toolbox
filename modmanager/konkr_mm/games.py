"""Definición de los juegos soportados y detección de sus rutas en Steam/Proton."""
import os
import re

GAMES = {
    "skyrimse": {
        "name": "Skyrim Special Edition",
        "appid": 489830,
        "nexus": "skyrimspecialedition",
        "appdata": "Skyrim Special Edition",   # %LOCALAPPDATA%\<appdata>\Plugins.txt
        "mygames": "Skyrim Special Edition",   # Documents\My Games\<mygames>
        "launcher": "SkyrimSELauncher.exe",
        "loader": "skse64_loader.exe",
        "se_name": "SKSE64",
        "star": True,
        "esl": True,          # plugins.txt con '*' para los activos
        "timestamps": False,   # orden por fecha de archivo (Oblivion)
        "custom_ini": None,
        "plugin_exts": (".esp", ".esm", ".esl"),
        "implicit": ["Skyrim.esm", "Update.esm", "Dawnguard.esm", "HearthFires.esm", "Dragonborn.esm"],
    },
    "fallout4": {
        "name": "Fallout 4",
        "appid": 377160,
        "nexus": "fallout4",
        "appdata": "Fallout4",
        "mygames": "Fallout4",
        "launcher": "Fallout4Launcher.exe",
        "loader": "f4se_loader.exe",
        "se_name": "F4SE",
        "star": True,
        "esl": True,
        "timestamps": False,
        "custom_ini": "Fallout4Custom.ini",
        "plugin_exts": (".esp", ".esm", ".esl"),
        "implicit": ["Fallout4.esm", "DLCRobot.esm", "DLCworkshop01.esm", "DLCCoast.esm",
                     "DLCworkshop02.esm", "DLCworkshop03.esm", "DLCNukaWorld.esm",
                     "DLCUltraHighResolution.esm"],
    },
    "oblivion": {
        "name": "Oblivion (original)",
        "appid": 22330,
        "nexus": "oblivion",
        "appdata": "Oblivion",
        "mygames": "Oblivion",
        "launcher": "OblivionLauncher.exe",
        "loader": "obse_loader.exe",
        "se_name": "xOBSE",
        "star": False,
        "esl": False,
        "timestamps": True,
        "custom_ini": None,
        "plugin_exts": (".esp", ".esm"),
        "implicit": [],
        "first": ["Oblivion.esm"],
    },
}

NEXUS_TO_GAME = {g["nexus"]: k for k, g in GAMES.items()}

STEAM_ROOT_CANDIDATES = [
    "~/.local/share/Steam",
    "~/.steam/steam",
    "~/.steam/root",
    "~/.var/app/com.valvesoftware.Steam/.local/share/Steam",
]


def find_steam_roots():
    seen, roots = set(), []
    for c in STEAM_ROOT_CANDIDATES:
        p = os.path.expanduser(c)
        if os.path.isdir(os.path.join(p, "steamapps")):
            real = os.path.realpath(p)
            if real not in seen:
                seen.add(real)
                roots.append(real)
    return roots


def library_folders(steam_root):
    libs = [steam_root]
    vdf = os.path.join(steam_root, "steamapps", "libraryfolders.vdf")
    try:
        with open(vdf, encoding="utf-8", errors="replace") as f:
            txt = f.read()
        for m in re.finditer(r'"path"\s+"([^"]+)"', txt):
            p = m.group(1).replace("\\\\", "\\")
            if os.path.isdir(p) and os.path.realpath(p) not in [os.path.realpath(x) for x in libs]:
                libs.append(p)
    except OSError:
        pass
    return libs


def ci_find(parent, name):
    """Devuelve la ruta real de `name` dentro de `parent` sin distinguir mayúsculas, o None."""
    try:
        exact = os.path.join(parent, name)
        if os.path.exists(exact):
            return exact
        low = name.lower()
        for e in os.listdir(parent):
            if e.lower() == low:
                return os.path.join(parent, e)
    except OSError:
        pass
    return None


def ci_path(base, *parts):
    """Resuelve una ruta componente a componente sin distinguir mayúsculas.
    Los componentes que no existen se devuelven tal cual."""
    cur = base
    for i, part in enumerate(parts):
        found = ci_find(cur, part)
        if found is None:
            return os.path.join(cur, *parts[i:])
        cur = found
    return cur


def detect_game(game_key):
    """Busca el juego en todas las bibliotecas de Steam. Devuelve dict o None."""
    g = GAMES[game_key]
    appid = g["appid"]
    for root in find_steam_roots():
        for lib in library_folders(root):
            acf = os.path.join(lib, "steamapps", f"appmanifest_{appid}.acf")
            if not os.path.isfile(acf):
                continue
            try:
                with open(acf, encoding="utf-8", errors="replace") as f:
                    m = re.search(r'"installdir"\s+"([^"]+)"', f.read())
            except OSError:
                m = None
            if not m:
                continue
            game_dir = os.path.join(lib, "steamapps", "common", m.group(1))
            if not os.path.isdir(game_dir):
                continue
            compat = None
            for base in (lib, root):
                c = os.path.join(base, "steamapps", "compatdata", str(appid))
                if os.path.isdir(c):
                    compat = c
                    break
            if compat is None:
                compat = os.path.join(lib, "steamapps", "compatdata", str(appid))
            return {"game_dir": game_dir, "compat_dir": compat, "library": lib, "steam_root": root}
    return None


def prefix_user_dir(compat_dir):
    return os.path.join(compat_dir, "pfx", "drive_c", "users", "steamuser")


def plugins_txt_path(game_key, compat_dir):
    g = GAMES[game_key]
    user = prefix_user_dir(compat_dir)
    folder = ci_path(user, "AppData", "Local", g["appdata"])
    found = ci_find(folder, "Plugins.txt")
    return found or os.path.join(folder, "Plugins.txt")


def mygames_dir(game_key, compat_dir):
    g = GAMES[game_key]
    return ci_path(prefix_user_dir(compat_dir), "Documents", "My Games", g["mygames"])
