"""Todo lo que tiene que ver con Steam: bibliotecas, juegos instalados, portadas,
opciones de lanzamiento (localconfig.vdf) y si Steam está abierto."""
import glob
import os
import re
import shutil
import subprocess
import time

from . import vdf

ROOT_CANDIDATES = [
    "~/.local/share/Steam",
    "~/.steam/steam",
    "~/.steam/root",
    "~/.var/app/com.valvesoftware.Steam/.local/share/Steam",
]
# herramientas que Steam instala como si fueran juegos
TOOL_NAME = re.compile(r"^(proton|steam linux runtime|steamworks|steamvr|steam audio)\b", re.I)
TOOL_APPIDS = {228980, 1070560, 1391110, 1628350, 1826330, 1493710, 2180100}


def steam_root():
    for c in ROOT_CANDIDATES:
        p = os.path.realpath(os.path.expanduser(c))
        if os.path.isdir(os.path.join(p, "steamapps")):
            return p
    return None


def libraries(root):
    libs = [root]
    try:
        data = vdf.loads(open(os.path.join(root, "steamapps", "libraryfolders.vdf"), encoding="utf-8",
                              errors="replace").read())
        lf = vdf.get_ci(data, "libraryfolders") or {}
        for v in lf.values():
            p = vdf.get_ci(v, "path") if isinstance(v, dict) else None
            if p and os.path.isdir(p) and os.path.realpath(p) not in map(os.path.realpath, libs):
                libs.append(p)
    except (OSError, vdf.VdfError):
        pass
    return libs


def installed_games(root=None):
    """Lista de juegos instalados: dicts con appid, name, installdir, library, game_dir, compat_dir."""
    root = root or steam_root()
    if not root:
        return []
    games = {}
    for lib in libraries(root):
        for acf in glob.glob(os.path.join(lib, "steamapps", "appmanifest_*.acf")):
            try:
                st = vdf.get_ci(vdf.loads(open(acf, encoding="utf-8", errors="replace").read()), "AppState") or {}
            except (OSError, vdf.VdfError):
                continue
            try:
                appid = int(vdf.get_ci(st, "appid", "0"))
            except ValueError:
                continue
            name = vdf.get_ci(st, "name", "") or f"App {appid}"
            if appid in TOOL_APPIDS or TOOL_NAME.match(name):
                continue
            installdir = vdf.get_ci(st, "installdir", "")
            compat = None
            for base in (lib, root):
                c = os.path.join(base, "steamapps", "compatdata", str(appid))
                if os.path.isdir(c):
                    compat = c
                    break
            games[appid] = {
                "appid": appid, "name": name, "installdir": installdir, "library": lib,
                "game_dir": os.path.join(lib, "steamapps", "common", installdir),
                "compat_dir": compat or os.path.join(lib, "steamapps", "compatdata", str(appid)),
                "proton": compat is not None,
            }
    return sorted(games.values(), key=lambda g: g["name"].lower())


def cover_image(appid, root=None):
    """Ruta de la cabecera (460x215) o la portada del juego en la caché de Steam."""
    root = root or steam_root()
    if not root:
        return None
    cache = os.path.join(root, "appcache", "librarycache")
    for pat in (f"{appid}_header.jpg", f"{appid}/header.jpg", f"{appid}/*/header.jpg",
                f"{appid}/library_header.jpg", f"{appid}_library_600x900.jpg", f"{appid}/library_600x900.jpg",
                f"{appid}/*/library_600x900.jpg", f"{appid}/*.jpg"):
        hits = glob.glob(os.path.join(cache, pat))
        if hits:
            return hits[0]
    return None


# --------------------------------------------------------------------------- opciones de lanzamiento

def localconfig_files(root=None):
    root = root or steam_root()
    if not root:
        return []
    files = glob.glob(os.path.join(root, "userdata", "*", "config", "localconfig.vdf"))
    return sorted(files, key=lambda p: os.path.getmtime(p), reverse=True)


def _apps_node(data, create=False):
    return vdf.find(data, "UserLocalConfigStore", "Software", "Valve", "Steam", "apps", create=create)


def get_launch_options(appid, root=None):
    for f in localconfig_files(root)[:1]:
        try:
            data = vdf.loads(open(f, encoding="utf-8", errors="replace").read())
        except (OSError, vdf.VdfError):
            return ""
        apps = _apps_node(data)
        app = vdf.get_ci(apps, str(appid)) if apps else None
        return vdf.get_ci(app, "LaunchOptions", "") if isinstance(app, dict) else ""
    return ""


def all_launch_options(root=None):
    out = {}
    for f in localconfig_files(root)[:1]:
        try:
            data = vdf.loads(open(f, encoding="utf-8", errors="replace").read())
        except (OSError, vdf.VdfError):
            return out
        apps = _apps_node(data) or {}
        for k, v in apps.items():
            if isinstance(v, dict) and k.isdigit():
                out[int(k)] = vdf.get_ci(v, "LaunchOptions", "")
    return out


def set_launch_options(changes, root=None, backup_dir=None):
    """changes: {appid: nuevo texto}. Escribe en todos los localconfig.vdf de los usuarios.
    Exige Steam cerrado (si no, Steam lo sobrescribe al salir)."""
    if steam_running():
        raise RuntimeError("steam-running")
    files = localconfig_files(root)
    if not files:
        raise RuntimeError("no-localconfig")
    for f in files:
        raw = open(f, encoding="utf-8", errors="replace").read()
        data = vdf.loads(raw)
        if backup_dir:
            os.makedirs(backup_dir, exist_ok=True)
            uid = os.path.basename(os.path.dirname(os.path.dirname(f)))
            shutil.copy2(f, os.path.join(backup_dir, f"localconfig-{uid}-{time.strftime('%Y%m%d-%H%M%S')}.vdf"))
            olds = sorted(glob.glob(os.path.join(backup_dir, f"localconfig-{uid}-*.vdf")))
            for o in olds[:-5]:
                os.remove(o)
        apps = _apps_node(data, create=True)
        for appid, text in changes.items():
            app = vdf.find(apps, str(appid), create=True)
            vdf.set_ci(app, "LaunchOptions", text)
        out = vdf.dumps(data)
        vdf.loads(out)  # comprobación: lo que escribimos se vuelve a leer bien
        tmp = f + ".kt-tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(out)
        os.replace(tmp, f)


def _log(msg):
    """Deja constancia en ~/.local/state/konkr-tweaks/steam.log (para diagnosticar)."""
    try:
        d = os.path.expanduser("~/.local/state/konkr-tweaks")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "steam.log"), "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")
    except OSError:
        pass


def _is_client(args, comm):
    """¿Es el proceso principal de Steam? El cliente es x86, así que en ARM corre bajo un
    traductor (FEX, box64…): se reconoce por la ruta del ejecutable en sus argumentos."""
    if "-shutdown" in args or "steam://exit" in args:   # la orden de cierre no cuenta
        return False
    if comm == "steam":
        return True
    for a in args[:3]:
        if a.endswith(("/ubuntu12_32/steam", "/ubuntu12_64/steam")) or os.path.basename(a) == "steam.sh":
            return True
    return False


def steam_pids():
    me = os.getpid()
    out = []
    try:
        pids = [int(p) for p in os.listdir("/proc") if p.isdigit()]
    except OSError:
        return out
    for pid in pids:
        if pid == me:
            continue
        try:
            with open(f"/proc/{pid}/stat", "rb") as f:
                if f.read().rsplit(b")", 1)[-1].split()[0] == b"Z":   # zombi: ya ha terminado
                    continue
            comm = open(f"/proc/{pid}/comm").read().strip()
            args = open(f"/proc/{pid}/cmdline", "rb").read().decode("utf-8", "replace").split("\0")
        except (OSError, IndexError):
            continue
        if _is_client(args, comm):
            out.append(pid)
    return out


def steam_running():
    return bool(steam_pids())


def in_game_mode():
    return "gamescope" in (os.environ.get("XDG_CURRENT_DESKTOP", "") + os.environ.get("XDG_SESSION_DESKTOP", "")).lower() \
        or bool(os.environ.get("GAMESCOPE_WAYLAND_DISPLAY"))


_LAST_CMD = []


def _remember_cmd():
    """Guarda cómo se arrancó Steam, para volver a abrirlo igual aunque no haya comando «steam»."""
    for pid in steam_pids():
        try:
            args = [a for a in open(f"/proc/{pid}/cmdline", "rb").read().decode("utf-8", "replace").split("\0") if a]
        except OSError:
            continue
        if args:
            _LAST_CMD[:] = args
            return


def _wait_closed(seconds):
    end = time.time() + seconds
    while time.time() < end:
        if not steam_running():
            time.sleep(2)            # margen para que termine de escribir sus archivos
            return not steam_running()
        time.sleep(1)
    return False


def shutdown_steam(timeout=45):
    """Cierra Steam de forma ordenada; si no responde, le pide salir con una señal."""
    if not steam_running():
        return True
    _remember_cmd()
    exe = shutil.which("steam")
    tried = []
    for cmd in ([exe, "-shutdown"] if exe else None, ["xdg-open", "steam://exit"]):
        if not cmd or (cmd[0] != exe and not shutil.which(cmd[0])):
            continue
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            tried.append(" ".join(cmd))
        except OSError as e:
            _log(f"no se pudo ejecutar {cmd}: {e}")
            continue
        if _wait_closed(timeout if len(tried) == 1 else 20):
            _log("Steam cerrado con: " + " ".join(cmd))
            return True
    for pid in steam_pids():            # último recurso: SIGTERM (Steam sale ordenadamente)
        try:
            os.kill(pid, 15)
            tried.append(f"SIGTERM {pid}")
        except OSError:
            pass
    ok = _wait_closed(25)
    _log(("Steam cerrado" if ok else "Steam NO se cerró") + " tras: " + "; ".join(tried) +
         ("" if ok else " | sigue abierto: " + ", ".join(map(str, steam_pids()))))
    return ok


def start_steam():
    """Vuelve a abrir Steam. Devuelve True si se lanzó algo."""
    exe = shutil.which("steam")
    options = []
    if exe:
        options.append([exe])
    if shutil.which("gtk-launch"):
        options.append(["gtk-launch", "steam"])
    if _LAST_CMD:
        options.append(list(_LAST_CMD))
    for cmd in options:
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
                             cwd=os.path.expanduser("~"))
            _log("Steam abierto con: " + " ".join(cmd))
            return True
        except OSError as e:
            _log(f"no se pudo abrir con {cmd}: {e}")
    _log("no hay forma de volver a abrir Steam")
    return False