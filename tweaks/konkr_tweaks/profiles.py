"""Perfiles por juego (JSON en profiles/ o en ~/.config/konkr-tweaks/profiles/).

{
  "appid": 489830,                 # o "match": {"glob": "..."} para perfiles genéricos (p. ej. Unreal)
  "name": "...", "experimental": false,
  "notes": {"es": "...", "en": "..."},
  "files": {
    "prefs": {"path": "{mygames}/Skyrim Special Edition/SkyrimPrefs.ini", "type": "ini"},
    "cfg":   {"path": ["{game}/a.cfg", "{home}/b.cfg"], "type": "cfg", "create": true, "lock": false,
              "only_existing": false, "quote": true}
  },
  "require": ["prefs"],             # archivos que tienen que existir (si no: «abre el juego una vez»)
  "presets": {"lowest": {"prefs": {...}}, "balanced": {...}, "quality": {...}},
  "fps_limit": {"file": "cfg", "on": {"fps_max": "{fps}"}, "off": {"fps_max": "300"}},   # límite dentro del juego
  "resolution": {"type": "ini|xml|call|kv|args", ...},
  "launch": {"fex": "fast", "ntsync": true, "deck": false, "fps": 0},   # recomendados
  "args": "-nologos"                # argumentos que el perfil añade al lanzar
}
Contenido de un preset según el tipo de archivo:
  ini  {"Sección": {"clave": "valor"}}         xml  {"graphics/TextureQuality": "0"}
  call {"TextureQuality": "\"Low\""}           kv   {"MaxFPS": "30"}
  cfg  {"r_shadows": "0"}                      reg  {"Software\\Empresa\\Juego": {"Prefijo": 0}}
  lines {"-opcion": true}
Un valor null borra la clave. Rutas: {game} {drive_c} {user} {documents} {mygames}
{appdata_local} {appdata_roaming} {home}. Se admiten comodines (*) y listas: vale la primera que exista.
"""
import glob
import json
import os
import shutil
import stat

from .editors import open_editor
from .settings import DATA_DIR, CONFIG_DIR, game_state, save_game_state

BUILTIN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "profiles")
USER_DIR = os.path.join(CONFIG_DIR, "profiles")
PRESET_ORDER = ["lowest", "balanced", "quality"]


def load_all():
    out = []
    for d in (BUILTIN_DIR, USER_DIR):
        for f in sorted(glob.glob(os.path.join(d, "*.json"))):
            try:
                with open(f, encoding="utf-8") as fh:
                    p = json.load(fh)
                p["_file"] = f
                out.append(p)
            except (OSError, ValueError):
                pass
    return out


def ci_path(path):
    """Resuelve una ruta absoluta componente a componente sin distinguir mayúsculas."""
    parts = [p for p in path.split("/") if p]
    cur = "/"
    for i, part in enumerate(parts):
        nxt = os.path.join(cur, part)
        if not os.path.exists(nxt):
            try:
                hit = next((e for e in os.listdir(cur) if e.lower() == part.lower()), None)
            except OSError:
                hit = None
            if hit is None:
                return os.path.join(cur, *parts[i:])
            nxt = os.path.join(cur, hit)
        cur = nxt
    return cur


def placeholders(game):
    drive_c = os.path.join(game.get("compat_dir", ""), "pfx", "drive_c")
    user = os.path.join(drive_c, "users", "steamuser")
    return {
        "game": game.get("game_dir", ""), "drive_c": drive_c, "user": user,
        "pfx": os.path.join(game.get("compat_dir", ""), "pfx"),
        "documents": os.path.join(user, "Documents"),
        "mygames": os.path.join(user, "Documents", "My Games"),
        "appdata_local": os.path.join(user, "AppData", "Local"),
        "appdata_roaming": os.path.join(user, "AppData", "Roaming"),
        "home": os.path.expanduser("~"),
    }


def resolve_path(template, game):
    """Primera ruta que exista entre las candidatas (con comodines); si ninguna existe, la primera."""
    cands = template if isinstance(template, list) else [template]
    first = None
    for t in cands:
        p = t.format(**placeholders(game))
        if any(c in p for c in "*?["):
            hits = sorted(glob.glob(p), key=lambda x: os.path.getmtime(x), reverse=True)
            if hits:
                return hits[0]
            continue
        p = ci_path(p)
        if first is None:
            first = p
        if os.path.exists(p):
            return p
    return first


def text(d, lang):
    if isinstance(d, str):
        return d
    if not isinstance(d, dict):
        return ""
    return d.get(lang) or d.get("en") or d.get("es") or next(iter(d.values()), "")


def _file_spec(spec):
    return {"path": spec, "type": "ini"} if isinstance(spec, (str, list)) else dict(spec)


class GameProfile:
    """Un perfil ligado a un juego concreto (con rutas resueltas)."""

    def __init__(self, profile, game, specs, paths):
        self.p = profile
        self.game = game
        self.specs = specs   # {id: spec}
        self.files = paths   # {id: ruta}

    @property
    def presets(self):
        pr = self.p.get("presets", {})
        return [k for k in PRESET_ORDER if k in pr] + [k for k in pr if k not in PRESET_ORDER]

    def missing_files(self):
        req = self.p.get("require", [f for f, s in self.specs.items() if not s.get("create")])
        return [fid for fid in req if not self.files.get(fid) or not os.path.isfile(self.files[fid])]

    def lockable(self):
        return any(s.get("lock") for s in self.specs.values())

    def backup_dir(self):
        return os.path.join(DATA_DIR, "backups", str(self.game["appid"]))

    def _backup(self, fid):
        path = self.files[fid]
        dst = os.path.join(self.backup_dir(), fid + ".orig")
        missing = os.path.join(self.backup_dir(), fid + ".absent")
        if os.path.exists(dst) or os.path.exists(missing):
            return
        os.makedirs(self.backup_dir(), exist_ok=True)
        if os.path.exists(path):
            shutil.copy2(path, dst)
        else:
            open(missing, "w").close()  # el archivo no existía: al restaurar se borra

    def has_backup(self):
        return any(os.path.exists(os.path.join(self.backup_dir(), fid + ext))
                   for fid in self.files for ext in (".orig", ".absent"))

    @staticmethod
    def _unlock(path):
        if os.path.exists(path):
            os.chmod(path, os.stat(path).st_mode | stat.S_IWUSR)

    def _apply_items(self, fid, items):
        spec = self.specs[fid]
        kind = spec.get("type", "ini")
        path = self.files[fid]
        self._unlock(path)
        ed = open_editor(kind, path)
        for item in items:
            if kind == "ini":
                sec, k, v = item
                ed.remove(sec, k) if v is None else ed.set(sec, k, v)
            elif kind == "reg":
                sec, k, v = item
                ed.set(sec, k, v)
            elif kind == "kv":
                k, v = item
                ed.set(k, v, only_existing=spec.get("only_existing", False), quote=spec.get("quote"))
            elif kind == "lines":
                k, v = item
                ed.set(k, bool(v))
            else:  # xml, call, cfg
                k, v = item
                ed.set(k, v)
        ed.save()

    def apply(self, preset=None, resolution=None, lock=False, fps=None):
        """Aplica un preset, una resolución ("1280x720") y/o un límite de fps del propio juego
        (fps=0 lo quita; None no lo toca). Devuelve los archivos tocados."""
        changes = {}
        fl = self.p.get("fps_limit")
        if fl and fps is not None and self.files.get(fl["file"]):
            vals = fl["on"] if fps > 0 else fl.get("off", {})
            kind = self.specs[fl["file"]].get("type", "ini")
            for k, v in vals.items():
                v = v.replace("{fps}", str(fps))
                if kind in ("ini", "reg"):
                    sec, key = k.rsplit("/", 1)
                    changes.setdefault(fl["file"], []).append((sec, key, v))
                else:
                    changes.setdefault(fl["file"], []).append((k, v))
        if preset:
            for fid, content in self.p["presets"][preset].items():
                kind = self.specs[fid].get("type", "ini")
                if kind in ("ini", "reg"):
                    for sec, kv in content.items():
                        for k, v in kv.items():
                            changes.setdefault(fid, []).append((sec, k, v))
                else:
                    for k, v in content.items():
                        changes.setdefault(fid, []).append((k, v))
        res = self.p.get("resolution") or {}
        st = game_state(self.game["appid"])
        if resolution and res:
            w, h = resolution.lower().split("x")
            rk = res.get("type", "ini")
            if rk == "ini":
                for key, val in ((res["width"], w), (res["height"], h)):
                    for k in (key if isinstance(key, list) else [key]):
                        changes.setdefault(res["file"], []).append((res["section"], k, val))
            elif rk == "xml":
                changes.setdefault(res["file"], []).extend([(res["width"], w), (res["height"], h)])
            elif rk in ("call", "kv", "cfg"):
                changes.setdefault(res["file"], []).append((res["key"], res["format"].format(w=w, h=h)))
            elif rk == "args":
                st["resolution_args"] = res["format"].format(w=w, h=h)
        touched = []
        for fid, items in changes.items():
            self._backup(fid)
            self._apply_items(fid, items)
            if lock and self.specs[fid].get("lock"):
                p = self.files[fid]
                os.chmod(p, os.stat(p).st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
            touched.append(self.files[fid])
        if preset:
            st["profile"] = preset
        if resolution:
            st["resolution"] = resolution
        st["profile_args"] = self.p.get("args", "")
        st["locked"] = bool(lock and self.lockable())
        save_game_state(self.game["appid"], st)
        return touched

    def restore(self):
        restored = []
        for fid, path in self.files.items():
            src = os.path.join(self.backup_dir(), fid + ".orig")
            absent = os.path.join(self.backup_dir(), fid + ".absent")
            self._unlock(path)
            if os.path.exists(src):
                shutil.copy2(src, path)
                restored.append(path)
            elif os.path.exists(absent) and os.path.exists(path):
                os.remove(path)
                restored.append(path)
        st = game_state(self.game["appid"])
        for k in ("profile", "resolution", "resolution_args", "profile_args", "locked", "mode"):
            st.pop(k, None)
        save_game_state(self.game["appid"], st)
        return restored

    def current_resolution(self):
        res = self.p.get("resolution")
        if not res:
            return None
        if res.get("type") == "args":
            return game_state(self.game["appid"]).get("resolution")
        path = self.files.get(res["file"])
        if not path or not os.path.isfile(path):
            return None
        rk = res.get("type", "ini")
        ed = open_editor(rk, path)
        if rk == "ini":
            wk = res["width"][0] if isinstance(res["width"], list) else res["width"]
            hk = res["height"][0] if isinstance(res["height"], list) else res["height"]
            w, h = ed.get(res["section"], wk), ed.get(res["section"], hk)
            return f"{w}x{h}" if w and h else None
        if rk == "xml":
            w, h = ed.get(res["width"]), ed.get(res["height"])
            return f"{w}x{h}" if w and h else None
        v = ed.get(res["key"])
        return v.replace(" ", "").replace(",", "x").strip('"') if v else None


def for_game(game, all_profiles=None):
    """Perfil para un juego: primero uno específico por appid, después los genéricos (p. ej. Unreal)."""
    all_profiles = all_profiles if all_profiles is not None else load_all()
    for p in all_profiles:
        ids = p.get("appid")
        if game["appid"] in (ids if isinstance(ids, list) else [ids]):
            specs = {fid: _file_spec(s) for fid, s in p.get("files", {}).items()}
            paths = {fid: resolve_path(s["path"], game) for fid, s in specs.items()}
            return GameProfile(p, game, specs, paths)
    if not os.path.isdir(game.get("compat_dir", "") or ""):
        return None
    for p in all_profiles:
        m = p.get("match")
        if not m:
            continue
        hits = sorted(glob.glob(m["glob"].format(**placeholders(game))))
        if not hits:
            continue
        base = os.path.dirname(hits[0])
        specs = {fid: _file_spec(s) for fid, s in p.get("files", {}).items()}
        paths = {fid: os.path.join(base, s["path"]) for fid, s in specs.items()}
        return GameProfile(p, game, specs, paths)
    return None
