#!/usr/bin/env python3
"""Mapeos de mando (Steam Input): busca archivos .vdf y los instala como plantillas de Steam.

Se ejecuta como el usuario normal. Salida: una línea JSON.

  ktb_maps.py list            .vdf encontrados, plantillas instaladas y juegos
  ktb_maps.py install RUTA    copia el .vdf a las plantillas de Steam (y una copia de seguridad)
  ktb_maps.py remove ARCHIVO  quita una plantilla instalada por el Toolbox
  ktb_maps.py restore         vuelve a poner las plantillas que haya borrado una actualización de Steam

Las plantillas viven en <Steam>/controller_base/templates y salen en «Explorar configuraciones →
Plantillas» de cualquier juego (también los no Steam). Una actualización de Steam puede borrar esa
carpeta, así que se guarda una copia en ~/mapeos-steam y cada «list» vuelve a poner las que falten.
"""
import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ktb_deps  # noqa: E402  (steam_root, games)

HOME = os.path.expanduser("~")
BACKUP = os.path.join(HOME, "mapeos-steam")
PREFIX = "konkr_"
MAX_FILES = 300
MAX_SIZE = 2 * 1024 * 1024
# Carpetas que no merece la pena recorrer (enormes o con .vdf internos de Steam)
SKIP = {".cache", ".git", "node_modules", "homebrew", ".steam", "Steam", "steamapps", "compatdata",
        "pfx", ".var", ".local", "mapeos-steam", "proc", "lost+found", ".Trash-1000", "shadercache"}


def out(data, code=0):
    print(json.dumps(data, ensure_ascii=False))
    return code


def templates_dir(root):
    return os.path.join(root, "controller_base", "templates")


def info(path):
    """Título y tipo de mando de un .vdf de Steam Input, o None si no lo es."""
    try:
        if os.path.getsize(path) > MAX_SIZE:
            return None
        text = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return None
    if '"controller_mappings"' not in text:
        return None
    t = re.search(r'"title"\s+"([^"]*)"', text)
    c = re.search(r'"controller_type"\s+"([^"]*)"', text)
    title = (t.group(1).strip() if t else "") or os.path.splitext(os.path.basename(path))[0]
    if title.startswith("#"):   # títulos localizados de Valve («#Title»)
        title = os.path.splitext(os.path.basename(path))[0]
    return {"title": title, "ctype": c.group(1) if c else ""}


def scan_roots():
    roots = [(HOME, 5)]
    for media in ("/run/media", "/media", "/mnt"):
        try:
            for d in os.listdir(media):
                full = os.path.join(media, d)
                if os.path.isdir(full):
                    # /run/media/<usuario>/<tarjeta> o /run/media/<tarjeta>
                    roots.append((full, 5))
        except OSError:
            pass
    return roots


def find_vdfs():
    found, seen = [], set()
    for root, depth in scan_roots():
        base = root.rstrip("/").count("/")
        for cur, dirs, files in os.walk(root, followlinks=False):
            if cur.rstrip("/").count("/") - base >= depth:
                dirs[:] = []
            else:
                dirs[:] = [d for d in dirs if d not in SKIP and not d.startswith(".")]
            for fn in files:
                if not fn.lower().endswith(".vdf"):
                    continue
                path = os.path.join(cur, fn)
                real = os.path.realpath(path)
                if real in seen:
                    continue
                seen.add(real)
                i = info(path)
                if not i:
                    continue
                try:
                    mtime = os.path.getmtime(path)
                except OSError:
                    mtime = 0
                folder = os.path.dirname(path)
                if folder.startswith(HOME):
                    folder = "~" + folder[len(HOME):]
                found.append({"path": path, "name": fn, "folder": folder, "mtime": mtime, **i})
                if len(found) >= MAX_FILES:
                    break
            if len(found) >= MAX_FILES:
                break
    found.sort(key=lambda f: -f["mtime"])
    return found


def safe_name(title, path):
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", title or os.path.splitext(os.path.basename(path))[0]).strip("_")
    return PREFIX + (stem[:60] or "mapeo") + ".vdf"


def restore_backups(tdir):
    """Vuelve a poner en Steam las plantillas que borró una actualización. -> cuántas."""
    n = 0
    try:
        names = os.listdir(BACKUP)
    except OSError:
        return 0
    os.makedirs(tdir, exist_ok=True)
    for fn in names:
        if fn.startswith(PREFIX) and fn.endswith(".vdf") and not os.path.exists(os.path.join(tdir, fn)):
            try:
                shutil.copyfile(os.path.join(BACKUP, fn), os.path.join(tdir, fn))
                n += 1
            except OSError:
                pass
    return n


def installed(tdir):
    res = []
    try:
        names = sorted(os.listdir(tdir))
    except OSError:
        return res
    for fn in names:
        if fn.startswith(PREFIX) and fn.endswith(".vdf"):
            i = info(os.path.join(tdir, fn)) or {"title": fn, "ctype": ""}
            res.append({"file": fn, **i})
    return res


def cmd_list(root):
    tdir = templates_dir(root)
    restored = restore_backups(tdir)
    games = [{"appid": g["appid"], "name": g["name"]} for g in ktb_deps.games(root)]
    tinst = installed(tdir)
    by_title = {t["title"] for t in tinst}
    files = find_vdfs()
    for f in files:
        f["installed"] = f["title"] in by_title
    return out({"ok": True, "files": files, "templates": tinst, "games": games, "restored": restored,
                "templates_dir": tdir})


def cmd_install(root, path):
    path = os.path.realpath(os.path.expanduser(path))
    i = info(path)
    if not i:
        return out({"ok": False, "error": "not-vdf"}, 1)
    tdir = templates_dir(root)
    os.makedirs(tdir, exist_ok=True)
    os.makedirs(BACKUP, exist_ok=True)
    name = safe_name(i["title"], path)
    shutil.copyfile(path, os.path.join(tdir, name))
    shutil.copyfile(path, os.path.join(BACKUP, name))
    return out({"ok": True, "file": name, "title": i["title"], "ctype": i["ctype"]})


def cmd_remove(root, name):
    name = os.path.basename(name)
    if not (name.startswith(PREFIX) and name.endswith(".vdf")):
        return out({"ok": False, "error": "not-ours"}, 1)
    removed = False
    for d in (templates_dir(root), BACKUP):
        p = os.path.join(d, name)
        if os.path.exists(p):
            os.remove(p)
            removed = True
    return out({"ok": removed, "error": None if removed else "missing"})


def main(argv):
    try:
        root = ktb_deps.steam_root()
        if not root:
            return out({"ok": False, "error": "no-steam"}, 1)
        cmd = argv[0] if argv else ""
        if cmd == "list":
            return cmd_list(root)
        if cmd == "restore":
            return out({"ok": True, "restored": restore_backups(templates_dir(root))})
        if cmd == "install" and len(argv) >= 2:
            return cmd_install(root, argv[1])
        if cmd == "remove" and len(argv) >= 2:
            return cmd_remove(root, argv[1])
        return out({"ok": False, "error": "bad-command"}, 1)
    except Exception as e:  # noqa — el plugin necesita siempre una respuesta JSON
        return out({"ok": False, "error": f"{type(e).__name__}: {e}"}, 1)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
