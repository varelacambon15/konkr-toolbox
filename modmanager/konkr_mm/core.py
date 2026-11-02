"""Núcleo del gestor: configuración, instalación de mods, despliegue, plugins y utilidades.
No depende de ninguna interfaz gráfica: lo usan la app GTK y (en el futuro) el companion web."""
import configparser
import filecmp
import functools
import json
import os
import shutil
import struct
import subprocess
import tempfile
import threading
import time
import uuid
import zipfile

from . import games as G
from .i18n import _

DATA_DIR = os.path.expanduser("~/.local/share/konkr-modmanager")
JUNK = {"__macosx", ".ds_store", "thumbs.db", "desktop.ini"}
DATA_FOLDERS = {
    "meshes", "textures", "scripts", "interface", "sound", "music", "seq", "strings", "materials",
    "skse", "f4se", "obse", "shadersfx", "video", "vis", "lodsettings", "grass", "facegen", "menus",
    "fonts", "shaders", "trees", "distantlod", "lsdata", "mcm", "nemesis_engine", "dyndolod",
    "netscriptframework", "calientetools", "skyproc patchers", "source", "dialogueviews", "platform",
    "programs", "f4se_plugins", "bodyslide", "tools", "lightplacer", "seasons", "sky", "terrain",
}
ARCHIVE_EXTS = (".bsa", ".ba2")
DOC_EXTS = (".txt", ".md", ".pdf", ".url", ".html", ".htm", ".jpg", ".jpeg", ".png", ".docx", ".rtf")
STATE_DIR_NAME = ".konkr-mm"
OBLIVION_EPOCH = 1136073600  # 2006-01-01


class ModError(Exception):
    pass


GAME_EXES = {
    "skyrimse": ("skyrimse.exe", "skse64_loader.exe"),
    "fallout4": ("fallout4.exe", "f4se_loader.exe"),
    "oblivion": ("oblivion.exe", "obse_loader.exe"),
}


def game_running(game_key):
    """True si el juego (o su script extender) se está ejecutando ahora mismo (vía /proc)."""
    names = GAME_EXES.get(game_key, ())
    try:
        pids = [p for p in os.listdir("/proc") if p.isdigit()]
    except OSError:
        return False
    for pid in pids:
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                cmd = f.read().replace(b"\0", b" ").decode("utf-8", "replace").lower()
        except OSError:
            continue
        for n in names:
            if n in cmd and "konkr_mm" not in cmd:
                return True
    return False


def locked(fn):
    """Serializa las operaciones que cambian el estado (interfaz, móvil y tareas comparten datos)."""
    @functools.wraps(fn)
    def wrapper(self, *a, **k):
        with self.mgr.lock:
            r = fn(self, *a, **k)
        self.mgr.notify(self.key)
        return r
    return wrapper


def _atomic_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".tmp-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def _load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def human_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def plugin_kind(path, esl=True):
    """'esm', 'esl' o 'esp' leyendo las flags de la cabecera TES4 (y la extensión).
    esl=False para Oblivion, que no tiene plugins ligeros."""
    ext = os.path.splitext(path)[1].lower()
    flags = 0
    try:
        with open(path, "rb") as f:
            head = f.read(12)
        if len(head) == 12 and head[:4] == b"TES4":
            flags = struct.unpack("<I", head[8:12])[0]
    except OSError:
        pass
    if esl and (ext == ".esl" or flags & 0x200):
        return "esl"
    if ext == ".esm" or flags & 0x1:
        return "esm"
    return "esp"


def stats_text(stats):
    """Resumen legible de lo que ha hecho apply()."""
    labels = {"added": _("nuevos"), "updated": _("actualizados"), "removed": _("quitados"),
              "conflicts": _("conflictos"), "backed_up": _("originales respaldados")}
    parts = [f"{v} {labels[k]}" for k, v in stats.items() if v and k in labels]
    return ", ".join(parts) if parts else _("Sin cambios.")


def is_master_kind(kind):
    return kind in ("esm", "esl")


# --------------------------------------------------------------------------- extracción

def _which(name):
    return shutil.which(name)


def extract_archive(archive, dest, log=print):
    os.makedirs(dest, exist_ok=True)
    attempts = []
    for exe in ("7z", "7zz", "7za"):
        if _which(exe):
            attempts.append((exe, [exe, "x", "-y", "-bd", f"-o{dest}", archive]))
    if _which("unar"):
        attempts.append(("unar", ["unar", "-q", "-f", "-D", "-o", dest, archive]))
    if _which("bsdtar"):
        attempts.append(("bsdtar", ["bsdtar", "-xf", archive, "-C", dest]))
    for name, cmd in attempts:
        try:
            r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=3600)
        except (OSError, subprocess.TimeoutExpired) as e:
            log("  " + _("{tool} falló: {error}", tool=name, error=e))
            continue
        if r.returncode == 0 and os.listdir(dest):
            return name
        log("  " + _("{tool} no pudo extraer (código {code}); probando otro método…", tool=name, code=r.returncode))
        shutil.rmtree(dest, ignore_errors=True)
        os.makedirs(dest, exist_ok=True)
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as z:
            z.extractall(dest)
        return "zipfile"
    try:
        import py7zr  # opcional
        with py7zr.SevenZipFile(archive) as z:
            z.extractall(dest)
        return "py7zr"
    except ImportError:
        pass
    except Exception as e:  # noqa
        log("  " + _("{tool} falló: {error}", tool="py7zr", error=e))
    raise ModError(_("No se ha podido descomprimir el archivo. Formatos: .zip, .7z, .rar "
                     "(necesita 7z, unar o bsdtar en el sistema)."))


def _entries(d):
    return [e for e in sorted(os.listdir(d)) if e.lower() not in JUNK]


def _looks_like_data(d, plugin_exts):
    for e in _entries(d):
        p = os.path.join(d, e)
        low = e.lower()
        if os.path.isdir(p) and low in DATA_FOLDERS:
            return True
        if os.path.isfile(p) and (low.endswith(plugin_exts) or low.endswith(ARCHIVE_EXTS)):
            return True
    return False


def _candidates(base, max_depth=4):
    out = []
    for root, dirs, _files in os.walk(base):
        rel = os.path.relpath(root, base)
        depth = 0 if rel == "." else rel.count(os.sep) + 1
        dirs[:] = [d for d in sorted(dirs) if d.lower() not in JUNK and d.lower() != "fomod"]
        if depth >= max_depth:
            dirs[:] = []
        out.append("" if rel == "." else rel.replace(os.sep, "/"))
    return out


def analyze_extracted(base, plugin_exts):
    """Decide qué carpeta del archivo es la raíz a instalar.
    Devuelve dict: root (ruta o None), kind ('data'|'root'|None), fomod (bool), candidates."""
    cur = base
    for _i in range(6):
        ents = _entries(cur)
        low = {e.lower(): e for e in ents}
        files = [e for e in ents if os.path.isfile(os.path.join(cur, e))]
        dirs = [e for e in ents if os.path.isdir(os.path.join(cur, e))]
        if "fomod" in low and os.path.isdir(os.path.join(cur, low["fomod"])):
            return {"root": None, "kind": None, "fomod": True, "candidates": _candidates(base)}
        if any(f.lower().endswith("_loader.exe") for f in files):
            return {"root": cur, "kind": "root", "fomod": False, "candidates": []}
        if _looks_like_data(cur, plugin_exts):
            return {"root": cur, "kind": "data", "fomod": False, "candidates": []}
        if "data" in low and os.path.isdir(os.path.join(cur, low["data"])):
            return {"root": os.path.join(cur, low["data"]), "kind": "data", "fomod": False, "candidates": []}
        if len(dirs) == 1 and all(f.lower().endswith((".txt", ".md", ".pdf", ".url", ".html", ".jpg", ".png"))
                                  for f in files):
            cur = os.path.join(cur, dirs[0])
            continue
        break
    return {"root": None, "kind": None, "fomod": False, "candidates": _candidates(base)}


def merge_move(src, dst):
    """Mueve el contenido de src dentro de dst, fusionando carpetas sin distinguir mayúsculas."""
    os.makedirs(dst, exist_ok=True)
    for e in os.listdir(src):
        if e.lower() in JUNK:
            continue
        s = os.path.join(src, e)
        existing = G.ci_find(dst, e)
        if os.path.isdir(s) and not os.path.islink(s):
            if existing and os.path.isdir(existing):
                merge_move(s, existing)
            else:
                if existing:
                    os.remove(existing)
                shutil.move(s, os.path.join(dst, e))
        else:
            if existing:
                if os.path.isdir(existing):
                    shutil.rmtree(existing)
                else:
                    os.remove(existing)
            shutil.move(s, existing or os.path.join(dst, e))


# --------------------------------------------------------------------------- manager

class Manager:
    def __init__(self, data_dir=DATA_DIR, log=print):
        self.data_dir = data_dir
        self.log = log
        os.makedirs(data_dir, exist_ok=True)
        self.config_path = os.path.join(data_dir, "config.json")
        self.config = _load_json(self.config_path, {})
        if self.config and "language" not in self.config:
            # instalaciones anteriores a la 0.3 se usaban en español: se mantiene
            self.config["language"] = "es"
        self.config.setdefault("games", {})
        self.config.setdefault("delete_archives", True)
        self._games = {}
        self.lock = threading.RLock()
        self.listeners = []

    def notify(self, game_key=None):
        for cb in list(self.listeners):
            try:
                cb(game_key)
            except Exception:  # noqa
                pass

    def save_config(self):
        _atomic_json(self.config_path, self.config)
        try:
            os.chmod(self.config_path, 0o600)  # contiene la clave de API
        except OSError:
            pass

    @property
    def api_key(self):
        return self.config.get("api_key", "")

    def set_api_key(self, key):
        self.config["api_key"] = key.strip()
        self.save_config()

    def game(self, key):
        if key not in self._games:
            self._games[key] = GameCtx(self, key)
        return self._games[key]


class GameCtx:
    def __init__(self, mgr, key):
        self.mgr = mgr
        self.key = key
        self.g = G.GAMES[key]
        self.cfg = mgr.config["games"].setdefault(key, {})
        self.state_path = os.path.join(mgr.data_dir, "games", key, "state.json")
        self.state = _load_json(self.state_path, {"mods": [], "plugins": []})
        self.state.setdefault("mods", [])
        self.state.setdefault("plugins", [])
        self.state.setdefault("dirty", False)
        if not self.cfg.get("game_dir"):
            self.detect()

    # ---- rutas -------------------------------------------------------------
    def log(self, msg):
        self.mgr.log(msg)

    @locked
    def detect(self):
        d = G.detect_game(self.key)
        if d:
            self.cfg.update({"game_dir": d["game_dir"], "compat_dir": d["compat_dir"],
                             "library": d["library"]})
            self.cfg.pop("plugins_txt", None)
            self.mgr.save_config()
        return d

    @locked
    def set_game_dir(self, path):
        """Ruta elegida a mano. Intenta deducir compatdata a partir de la biblioteca."""
        self.cfg["game_dir"] = path
        lib = os.path.dirname(os.path.dirname(os.path.dirname(path)))  # .../steamapps/common/X
        compat = os.path.join(lib, "steamapps", "compatdata", str(self.g["appid"]))
        if os.path.isdir(compat):
            self.cfg["compat_dir"] = compat
            self.cfg["library"] = lib
        self.mgr.save_config()

    @property
    def game_dir(self):
        return self.cfg.get("game_dir")

    @property
    def found(self):
        return bool(self.game_dir) and os.path.isdir(self.game_dir)

    @property
    def data_path(self):
        return G.ci_path(self.game_dir, "Data")

    @property
    def compat_dir(self):
        return self.cfg.get("compat_dir")

    @property
    def prefix_ok(self):
        return bool(self.compat_dir) and os.path.isdir(G.prefix_user_dir(self.compat_dir))

    @property
    def plugins_txt(self):
        if self.cfg.get("plugins_txt"):
            return self.cfg["plugins_txt"]
        if not self.compat_dir:
            return None
        return G.plugins_txt_path(self.key, self.compat_dir)

    @property
    def staging(self):
        """Carpeta de mods descomprimidos. Si es posible, en el mismo disco que el juego para
        poder usar enlaces duros (no ocupan espacio dos veces)."""
        if self.cfg.get("staging_dir"):
            return self.cfg["staging_dir"]
        default = os.path.join(self.mgr.data_dir, "staging", self.key)
        lib = self.cfg.get("library")
        if lib and self.found:
            try:
                home_dev = os.stat(self.mgr.data_dir).st_dev
                if os.stat(self.game_dir).st_dev != home_dev:
                    return os.path.join(lib, "konkr-modmanager", self.key)
            except OSError:
                pass
        return default

    @property
    def downloads(self):
        return os.path.join(os.path.dirname(self.staging), "downloads")

    @property
    def meta_dir(self):
        return os.path.join(self.game_dir, STATE_DIR_NAME)

    def mod_dir(self, mod):
        return os.path.join(self.staging, "mods", mod["id"])

    def save(self):
        _atomic_json(self.state_path, self.state)

    def mark_dirty(self):
        self.state["dirty"] = True
        self.save()

    # ---- mods --------------------------------------------------------------
    @property
    def mods(self):
        return self.state["mods"]

    def get_mod(self, mod_id):
        for m in self.mods:
            if m["id"] == mod_id:
                return m
        raise ModError(_("Mod no encontrado"))

    def install_archive(self, archive, name=None, source=None, version="", chooser=None, progress=None,
                        delete_archive=False, replace_id=None):
        """Instala un .zip/.7z/.rar en staging. chooser(tmpdir, analysis) se llama si no se sabe
        qué carpeta instalar (o si es un FOMOD) y debe devolver {'roots': [...], 'kind': ...} o None."""
        if not self.found:
            raise ModError(_("Primero detecta o elige la carpeta del juego."))
        progress = progress or (lambda f, t: None)
        tmp = os.path.join(self.staging, "tmp", uuid.uuid4().hex[:8])
        try:
            progress(None, _("Descomprimiendo…"))
            self.log(_("Descomprimiendo {file}", file=os.path.basename(archive)))
            tool = extract_archive(archive, tmp, self.log)
            self.log("  " + _("extraído con {tool}", tool=tool))
            an = analyze_extracted(tmp, self.g["plugin_exts"])
            if an["root"]:
                roots, kind = [an["root"]], an["kind"]
            else:
                if chooser is None:
                    raise ModError(_("No se reconoce la estructura del mod y no hay selector disponible."))
                choice = chooser(tmp, an)
                if not choice:
                    self.log("  " + _("instalación cancelada"))
                    return None
                roots = [os.path.join(tmp, r) if not os.path.isabs(r) else r for r in choice["roots"]]
                kind = choice.get("kind", "data")
            mod = {
                "id": uuid.uuid4().hex[:12],
                "name": name or os.path.splitext(os.path.basename(archive))[0],
                "version": version or "",
                "enabled": True,
                "kind": kind,
                "source": source or {"type": "file", "archive": os.path.basename(archive)},
                "installed": time.strftime("%Y-%m-%d %H:%M"),
                "installed_ts": int(time.time()),
            }
            dest = self.mod_dir(mod)
            progress(None, _("Copiando archivos…"))
            for r in roots:
                merge_move(r, dest)
            # fuera léeme/capturas sueltos en la raíz del mod (no los usa el juego)
            for f in os.listdir(dest):
                p = os.path.join(dest, f)
                if os.path.isfile(p) and f.lower().endswith(DOC_EXTS):
                    os.remove(p)
            self._scan_mod(mod)
            with self.mgr.lock:
                old = next((m for m in self.mods if m["id"] == replace_id), None) if replace_id else None
                if old:
                    # actualización: mismo puesto en la lista y mismo estado activado
                    mod["enabled"] = old["enabled"]
                    idx = self.mods.index(old)
                    self.mods[idx] = mod
                    shutil.rmtree(self.mod_dir(old), ignore_errors=True)
                    self.log(_("«{name}» sustituido por la versión nueva", name=old["name"]))
                else:
                    self.mods.append(mod)
                self.sync_plugins()
                self.mark_dirty()
            self.mgr.notify(self.key)
            self.log(_("Instalado «{name}»: {n} archivos, {size}", name=mod["name"], n=mod["files"],
                       size=human_size(mod["size"]))
                     + (", plugins: " + ", ".join(mod["plugins"]) if mod["plugins"] else "")
                     + (" [" + _("raíz del juego") + "]" if kind == "root" else ""))
            if delete_archive:
                try:
                    os.remove(archive)
                except OSError:
                    pass
            return mod
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def _mod_data_dir(self, mod):
        d = self.mod_dir(mod)
        return d if mod["kind"] == "data" else G.ci_path(d, "Data")

    def _scan_mod(self, mod):
        d = self.mod_dir(mod)
        n, size = 0, 0
        for root, _dirs, files in os.walk(d):
            for f in files:
                n += 1
                try:
                    size += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass
        mod["files"], mod["size"] = n, size
        plugins, kinds = [], {}
        dd = self._mod_data_dir(mod)
        if os.path.isdir(dd):
            for f in sorted(os.listdir(dd)):
                p = os.path.join(dd, f)
                if os.path.isfile(p) and f.lower().endswith(self.g["plugin_exts"]):
                    plugins.append(f)
                    kinds[f] = plugin_kind(p, self.g["esl"])
        mod["plugins"], mod["plugin_kinds"] = plugins, kinds

    @locked
    def remove_mod(self, mod_id):
        mod = self.get_mod(mod_id)
        shutil.rmtree(self.mod_dir(mod), ignore_errors=True)
        self.state["mods"] = [m for m in self.mods if m["id"] != mod_id]
        self.sync_plugins()
        self.mark_dirty()
        self.log(_("Eliminado «{name}» (pulsa Aplicar para quitarlo del juego)", name=mod["name"]))

    @locked
    def set_enabled(self, mod_id, enabled):
        self.get_mod(mod_id)["enabled"] = bool(enabled)
        self.sync_plugins()
        self.mark_dirty()

    @locked
    def move_mod(self, mod_id, delta):
        mods = self.mods
        i = next(i for i, m in enumerate(mods) if m["id"] == mod_id)
        j = max(0, min(len(mods) - 1, i + delta))
        if i != j:
            mods.insert(j, mods.pop(i))
            self.sync_plugins()
            self.mark_dirty()
        return j

    @locked
    def rename_mod(self, mod_id, name):
        self.get_mod(mod_id)["name"] = name
        self.save()

    # ---- plugins -----------------------------------------------------------
    def _available_plugins(self):
        out, seen = [], set()
        for m in self.mods:
            if not m["enabled"]:
                continue
            for p in m.get("plugins", []):
                if p.lower() not in seen:
                    seen.add(p.lower())
                    out.append((p, m.get("plugin_kinds", {}).get(p, "esp"), m["name"]))
        return out

    def sync_plugins(self):
        avail = self._available_plugins()
        by_low = {p.lower(): (p, k, mn) for p, k, mn in avail}
        old = [e for e in self.state["plugins"] if e["name"].lower() in by_low]
        known = {e["name"].lower() for e in old}
        for p, k, _mn in avail:
            if p.lower() in known:
                continue
            entry = {"name": p, "active": True}
            if is_master_kind(k):
                idx = 0
                for i, e in enumerate(old):
                    if is_master_kind(by_low[e["name"].lower()][1]):
                        idx = i + 1
                old.insert(idx, entry)
            else:
                old.append(entry)
            known.add(p.lower())
        for e in old:
            p, k, mn = by_low[e["name"].lower()]
            e["kind"], e["mod"] = k, mn
        self.state["plugins"] = old

    @locked
    def move_plugin(self, name, delta):
        pl = self.state["plugins"]
        i = next(i for i, e in enumerate(pl) if e["name"] == name)
        j = max(0, min(len(pl) - 1, i + delta))
        if i != j:
            pl.insert(j, pl.pop(i))
            self.mark_dirty()
        return j

    @locked
    def set_plugin_active(self, name, active):
        for e in self.state["plugins"]:
            if e["name"] == name:
                e["active"] = bool(active)
        self.mark_dirty()

    # ---- despliegue --------------------------------------------------------
    def _manifest_path(self):
        return os.path.join(self.meta_dir, "manifest.json")

    def load_manifest(self):
        m = _load_json(self._manifest_path(), {})
        m.setdefault("files", {})
        m.setdefault("backups", {})
        m.setdefault("dirs", [])
        m.setdefault("plugins", [])
        return m

    def _save_manifest(self, man):
        _atomic_json(self._manifest_path(), man)

    @locked
    def apply(self, progress=None):
        """Sincroniza la carpeta del juego con los mods activados (en orden: el último gana)."""
        if not self.found:
            raise ModError(_("No se encuentra la carpeta del juego."))
        self._check_not_running()
        progress = progress or (lambda f, t: None)
        gd = self.game_dir
        man = self.load_manifest()
        listing = {}

        def lst(d):
            if d not in listing:
                try:
                    listing[d] = {e.lower(): e for e in os.listdir(d)}
                except OSError:
                    listing[d] = {}
            return listing[d]

        def resolve(rel, create):
            parts = rel.split("/")
            cur, built = gd, []
            for part in parts[:-1]:
                ents = lst(cur)
                name = ents.get(part.lower())
                if name is None:
                    if not create:
                        return None
                    os.mkdir(os.path.join(cur, part))
                    ents[part.lower()] = part
                    listing[os.path.join(cur, part)] = {}
                    name = part
                    man["dirs"].append("/".join(built + [part]))
                cur = os.path.join(cur, name)
                built.append(name)
            name = lst(cur).get(parts[-1].lower(), parts[-1])
            return "/".join(built + [name])

        # 1) mapa deseado
        progress(None, _("Calculando cambios…"))
        desired, conflicts = {}, 0
        for mod in self.mods:
            if not mod["enabled"]:
                continue
            md = self.mod_dir(mod)
            if not os.path.isdir(md):
                self.log(_("AVISO: faltan los archivos de «{name}», se omite", name=mod["name"]))
                continue
            prefix = "Data/" if mod["kind"] == "data" else ""
            for root, _dirs, files in os.walk(md):
                for f in files:
                    src = os.path.join(root, f)
                    rel = prefix + os.path.relpath(src, md).replace(os.sep, "/")
                    k = rel.lower()
                    if k in desired:
                        conflicts += 1
                    desired[k] = (mod["id"], src, rel)

        stats = {"added": 0, "updated": 0, "removed": 0, "unchanged": 0,
                 "conflicts": conflicts, "backed_up": 0}
        backup_root = os.path.join(self.meta_dir, "backup")

        # 2) quitar lo que ya no toca
        to_remove = [k for k in man["files"] if k not in desired]
        for i, k in enumerate(to_remove):
            entry = man["files"].pop(k)
            p = os.path.join(gd, entry["path"])
            try:
                os.remove(p)
            except FileNotFoundError:
                pass
            if k in man["backups"]:
                b = os.path.join(backup_root, man["backups"].pop(k))
                if os.path.exists(b):
                    os.replace(b, p)
            stats["removed"] += 1
            if i % 200 == 0:
                progress(i / max(1, len(to_remove)) * 0.2, _("Quitando archivos… {i}/{n}", i=i, n=len(to_remove)))

        # 3) añadir / actualizar
        items = list(desired.items())
        total = len(items)
        for i, (k, (mod_id, src, rel)) in enumerate(items):
            if i % 100 == 0:
                progress(0.2 + 0.75 * i / max(1, total), _("Instalando en el juego… {i}/{n}", i=i, n=total))
                if i % 1000 == 0 and i:
                    self._save_manifest(man)
            st = os.stat(src)
            entry = man["files"].get(k)
            if entry:
                tgt = os.path.join(gd, entry["path"])
                if entry["mod"] == mod_id and os.path.exists(tgt) and (
                        _samefile(src, tgt) or (entry["size"] == st.st_size and entry["mtime"] == st.st_mtime_ns)):
                    stats["unchanged"] += 1
                    continue
            real_rel = resolve(rel, create=True)
            tgt = os.path.join(gd, real_rel)
            if os.path.lexists(tgt):
                if k not in man["files"]:
                    # archivo original del juego (o puesto a mano): se guarda copia
                    b = os.path.join(backup_root, real_rel)
                    os.makedirs(os.path.dirname(b), exist_ok=True)
                    os.replace(tgt, b)
                    man["backups"][k] = real_rel
                    stats["backed_up"] += 1
                else:
                    os.remove(tgt)
                stats["updated"] += 1
            else:
                stats["added"] += 1
            try:
                os.link(src, tgt)
            except OSError:
                shutil.copy2(src, tgt)
            lst(os.path.dirname(tgt))[os.path.basename(tgt).lower()] = os.path.basename(tgt)
            man["files"][k] = {"path": real_rel, "mod": mod_id, "size": st.st_size, "mtime": st.st_mtime_ns}

        self._cleanup_dirs(man)
        self._save_manifest(man)
        progress(0.97, _("Escribiendo plugins.txt…"))
        self.write_plugins(man)
        self._save_manifest(man)
        self.state["dirty"] = False
        self.save()
        progress(1.0, _("Hecho"))
        self.log(_("Aplicado: {stats}", stats=stats_text(stats)))
        return stats

    def _check_not_running(self):
        if game_running(self.key):
            raise ModError(_("{game} está abierto. Ciérralo antes de aplicar cambios.", game=self.g["name"]))

    def snapshot(self):
        """Copia del estado para la API del móvil."""
        with self.mgr.lock:
            st = json.loads(json.dumps(self.state))
        se = self.se_status() if self.found else {}
        return {
            "key": self.key, "name": self.g["name"], "nexus": self.g["nexus"], "found": self.found,
            "prefix_ok": self.prefix_ok, "dirty": st.get("dirty", False),
            "mods": [{k: m.get(k) for k in ("id", "name", "version", "enabled", "kind", "files", "size",
                                             "plugins", "source", "installed")} for m in st["mods"]],
            "plugins": st["plugins"],
            "se": {"name": self.g["se_name"], "installed": bool(se.get("loader")),
                   "active": bool(se.get("swapped")), "can_restore": bool(se.get("orig"))},
            "running": game_running(self.key),
        }

    def _cleanup_dirs(self, man):
        keep = []
        for d in sorted(set(man["dirs"]), key=lambda s: -s.count("/")):
            p = os.path.join(self.game_dir, d)
            try:
                if os.path.isdir(p) and not os.listdir(p):
                    os.rmdir(p)
                    continue
            except OSError:
                pass
            if os.path.isdir(p):
                keep.append(d)
        man["dirs"] = keep

    @locked
    def purge(self, progress=None):
        """Quita del juego todo lo que ha puesto el gestor y restaura los originales."""
        progress = progress or (lambda f, t: None)
        if not self.found:
            raise ModError(_("No se encuentra la carpeta del juego."))
        self._check_not_running()
        if self.se_status().get("swapped"):
            self.se_restore()
        man = self.load_manifest()
        gd = self.game_dir
        backup_root = os.path.join(self.meta_dir, "backup")
        keys = list(man["files"].keys())
        for i, k in enumerate(keys):
            entry = man["files"].pop(k)
            p = os.path.join(gd, entry["path"])
            try:
                os.remove(p)
            except FileNotFoundError:
                pass
            if k in man["backups"]:
                b = os.path.join(backup_root, man["backups"].pop(k))
                if os.path.exists(b):
                    os.replace(b, p)
            if i % 200 == 0:
                progress(i / max(1, len(keys)), _("Quitando… {i}/{n}", i=i, n=len(keys)))
        self._cleanup_dirs(man)
        saved = self.state["plugins"]
        self.state["plugins"] = []
        try:
            self.write_plugins(man)
        finally:
            self.state["plugins"] = saved
        self._save_manifest(man)
        self.state["dirty"] = True
        self.save()
        progress(1.0, _("Hecho"))
        self.log(_("Juego restaurado: quitados {n} archivos del gestor", n=len(keys)))
        return len(keys)

    # ---- plugins.txt --------------------------------------------------------
    def read_plugins_txt(self):
        path = self.plugins_txt
        out = []
        if not path or not os.path.isfile(path):
            return out
        with open(path, "rb") as f:
            raw = f.read()
        try:
            txt = raw.decode("utf-8")
        except UnicodeDecodeError:
            txt = raw.decode("cp1252", errors="replace")
        for line in txt.splitlines():
            line = line.strip().lstrip("﻿")
            if not line or line.startswith("#"):
                continue
            if self.g["star"]:
                out.append((line.lstrip("*"), line.startswith("*")))
            else:
                out.append((line, True))
        return out

    def write_plugins(self, man):
        path = self.plugins_txt
        if not path or not self.prefix_ok:
            self.log(_("AVISO: no existe todavía el prefijo de Proton del juego; ábrelo una vez desde "
                       "Steam y vuelve a pulsar Aplicar para escribir plugins.txt."))
            return
        managed = [e for e in self.state["plugins"]]
        managed_low = {e["name"].lower() for e in managed} | {p.lower() for p in man.get("plugins", [])}
        implicit_low = {p.lower() for p in self.g["implicit"]}
        existing = self.read_plugins_txt()
        unmanaged = [(n, a) for n, a in existing
                     if n.lower() not in managed_low and n.lower() not in implicit_low]
        final = unmanaged + [(e["name"], e["active"]) for e in managed]
        first = [p for p in self.g.get("first", [])]
        if first:
            final = [(p, True) for p in first] + [x for x in final if x[0].lower() not in {f.lower() for f in first}]
        data = self.data_path

        def master(name):
            for e in managed:
                if e["name"] == name:
                    return is_master_kind(e.get("kind", "esp"))
            p = G.ci_find(data, name)
            return is_master_kind(plugin_kind(p, self.g["esl"])) if p else name.lower().endswith((".esm", ".esl"))

        final = [x for x in final if master(x[0])] + [x for x in final if not master(x[0])]
        os.makedirs(os.path.dirname(path), exist_ok=True)
        orig = os.path.join(self.meta_dir, "Plugins.txt.orig")
        if os.path.isfile(path) and not os.path.exists(orig):
            os.makedirs(self.meta_dir, exist_ok=True)
            shutil.copy2(path, orig)
        lines = [] if self.g["timestamps"] else [
            "# This file is used by the game to keep track of your downloaded content.",
            "# Please do not modify this file."]
        for name, active in final:
            if self.g["star"]:
                lines.append(("*" if active else "") + name)
            elif active:
                lines.append(name)
        with open(path, "w", encoding="cp1252", errors="replace", newline="\r\n") as f:
            f.write("\n".join(lines) + "\n")
        man["plugins"] = [e["name"] for e in managed]
        if self.g["timestamps"]:
            n = 0
            for i, (name, _a) in enumerate(final):
                p = G.ci_find(data, name)
                if p:
                    t = OBLIVION_EPOCH + i * 60
                    try:
                        os.utime(p, (t, t))
                        n += 1
                    except OSError:
                        pass
            self.log("  " + _("orden por fecha aplicado a {n} plugins (Oblivion)", n=n))
        self.log("  " + _("plugins.txt escrito ({n} entradas)", n=len(final)))

    # ---- script extender ------------------------------------------------------
    def se_status(self):
        if not self.found:
            return {}
        loader = G.ci_find(self.game_dir, self.g["loader"])
        launcher = G.ci_find(self.game_dir, self.g["launcher"])
        orig = os.path.join(self.meta_dir, self.g["launcher"] + ".orig")
        swapped = bool(loader and launcher and os.path.exists(orig) and
                       filecmp.cmp(loader, launcher, shallow=False))
        return {"loader": loader, "launcher": launcher, "orig": orig if os.path.exists(orig) else None,
                "swapped": swapped}

    @locked
    def se_enable(self):
        s = self.se_status()
        if not s.get("loader"):
            raise ModError(_("No está instalado {se} ({loader} no está en la carpeta del juego). "
                             "Instálalo como mod y pulsa Aplicar primero.", se=self.g["se_name"], loader=self.g["loader"]))
        launcher = s["launcher"] or os.path.join(self.game_dir, self.g["launcher"])
        os.makedirs(self.meta_dir, exist_ok=True)
        orig = os.path.join(self.meta_dir, self.g["launcher"] + ".orig")
        if not os.path.exists(orig) and os.path.exists(launcher) and \
                not filecmp.cmp(s["loader"], launcher, shallow=False):
            shutil.copy2(launcher, orig)
        tmp = launcher + ".kmm-tmp"
        shutil.copyfile(s["loader"], tmp)
        os.replace(tmp, launcher)
        self.log(_("{se} activado: {launcher} ahora arranca {loader}", se=self.g["se_name"],
                   launcher=self.g["launcher"], loader=self.g["loader"]))

    @locked
    def se_restore(self):
        s = self.se_status()
        orig = os.path.join(self.meta_dir, self.g["launcher"] + ".orig")
        if not os.path.exists(orig):
            raise ModError(_("No hay copia del launcher original. Si hace falta, usa «Verificar "
                             "integridad de los archivos» en Steam."))
        launcher = s.get("launcher") or os.path.join(self.game_dir, self.g["launcher"])
        shutil.copy2(orig, launcher)
        self.log(_("Launcher original de {game} restaurado", game=self.g["name"]))

    # ---- INI ----------------------------------------------------------------
    def _ini_set(self, path, values):
        cp = configparser.ConfigParser(strict=False, interpolation=None)
        cp.optionxform = str
        if os.path.isfile(path):
            bak = path + ".kmm-orig"
            if not os.path.exists(bak):
                shutil.copy2(path, bak)
            with open(path, encoding="utf-8", errors="replace") as f:
                cp.read_string(f.read().lstrip("﻿"))
        for section, kv in values.items():
            if not cp.has_section(section):
                cp.add_section(section)
            for k, v in kv.items():
                for existing in list(cp[section].keys()):
                    if existing.lower() == k.lower() and existing != k:
                        cp.remove_option(section, existing)
                cp.set(section, k, v)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\r\n") as f:
            cp.write(f, space_around_delimiters=False)

    @locked
    def fix_loose_files_ini(self):
        """Fallout 4: permite que los archivos sueltos de los mods (texturas, etc.) se carguen
        y que se respete plugins.txt."""
        if self.key != "fallout4":
            raise ModError(_("Solo hace falta en Fallout 4."))
        if not self.prefix_ok:
            raise ModError(_("Abre Fallout 4 una vez desde Steam para que se cree el prefijo."))
        d = G.mygames_dir(self.key, self.compat_dir)
        custom = G.ci_find(d, "Fallout4Custom.ini") or os.path.join(d, "Fallout4Custom.ini")
        self._ini_set(custom, {"Archive": {"bInvalidateOlderFiles": "1", "sResourceDataDirsFinal": ""}})
        prefs = G.ci_find(d, "Fallout4Prefs.ini") or os.path.join(d, "Fallout4Prefs.ini")
        self._ini_set(prefs, {"Launcher": {"bEnableFileSelection": "1"}})
        self.log(_("INI de Fallout 4 ajustados (archivos sueltos y selección de plugins activados)"))


def _samefile(a, b):
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False
