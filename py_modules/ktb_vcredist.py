#!/usr/bin/env python3
"""Instala Microsoft Visual C++ 2015-2022 (arm64, x64 o x86) en el prefijo de Proton de un juego.

Se ejecuta siempre como el usuario normal (no como root), para que el prefijo siga siendo suyo.
Salida: una línea JSON.

  ktb_vcredist.py games                       juegos con prefijo y el Proton que usan
  ktb_vcredist.py install APPID ARCH          descarga (si hace falta) e instala; ARCH = arm64|x64|x86
"""
import json
import os
import re
import struct
import subprocess
import sys
import time
import zlib
import urllib.request

HOME = os.path.expanduser("~")
CACHE = os.path.join(HOME, ".cache", "konkr-toolbox")
LOG = os.path.join(CACHE, "vcredist.log")
URLS = {
    "arm64": "https://aka.ms/vs/17/release/vc_redist.arm64.exe",
    "x64": "https://aka.ms/vs/17/release/vc_redist.x64.exe",
    "x86": "https://aka.ms/vs/17/release/vc_redist.x86.exe",
}
# Códigos de salida del instalador de Microsoft que significan «correcto»
# (el sistema operativo solo conserva el último byte del código: 1638 → 102, 3010 → 194)
OK_CODES = {0: "ok", 1638: "already", 3010: "reboot", 102: "already", 194: "reboot"}


def out(data, code=0):
    print(json.dumps(data, ensure_ascii=False))
    return code


def steam_root():
    for p in (".local/share/Steam", ".steam/steam", ".steam/root", ".var/app/com.valvesoftware.Steam/.local/share/Steam"):
        full = os.path.join(HOME, p)
        if os.path.isdir(os.path.join(full, "steamapps")):
            return os.path.realpath(full)
    return None


def libraries(root):
    libs = [root]
    try:
        text = open(os.path.join(root, "steamapps", "libraryfolders.vdf"), encoding="utf-8", errors="replace").read()
        for m in re.finditer(r'"path"\s+"([^"]+)"', text):
            p = m.group(1).replace("\\\\", "\\")
            if p not in libs and os.path.isdir(os.path.join(p, "steamapps")):
                libs.append(p)
    except OSError:
        pass
    return libs


def shortcuts(root):
    """Juegos añadidos a Steam como «no Steam» (userdata/*/config/shortcuts.vdf, VDF binario)."""
    res = {}
    try:
        users = os.listdir(os.path.join(root, "userdata"))
    except OSError:
        return res
    for u in users:
        path = os.path.join(root, "userdata", u, "config", "shortcuts.vdf")
        try:
            data = open(path, "rb").read()
        except OSError:
            continue
        for e in _parse_shortcuts(data):
            name, exe = e.get("appname") or e.get("name") or "", e.get("exe") or ""
            appid = e.get("appid")
            if appid is None:
                appid = zlib.crc32((exe + name).encode("utf-8")) | 0x80000000
            appid &= 0xFFFFFFFF
            if name:
                res[appid] = name
    return res


def _parse_shortcuts(data):
    """Lee las entradas de un shortcuts.vdf. -> lista de {clave en minúsculas: valor}."""
    entries, i, n = [], 0, len(data)

    def cstr():
        nonlocal i
        j = data.find(b"\0", i)
        if j < 0:
            j = n
        v = data[i:j].decode("utf-8", "replace")
        i = j + 1
        return v

    def read_map():
        nonlocal i
        out = {}
        while i < n:
            t = data[i]
            i += 1
            if t == 8:
                return out
            key = cstr().lower()
            if t == 0:
                out[key] = read_map()
            elif t == 1:
                out[key] = cstr()
            elif t == 2:
                out[key] = struct.unpack_from("<I", data, i)[0]
                i += 4
            else:
                return out
        return out

    try:
        top = read_map()
    except (struct.error, IndexError):
        return entries
    block = top.get("shortcuts", top)
    if isinstance(block, dict):
        entries = [v for v in block.values() if isinstance(v, dict)]
    return entries


def games(root):
    found = {}
    for lib in libraries(root):
        sa = os.path.join(lib, "steamapps")
        try:
            names = os.listdir(sa)
        except OSError:
            continue
        for fn in names:
            m = re.match(r"appmanifest_(\d+)\.acf$", fn)
            if not m:
                continue
            appid = int(m.group(1))
            try:
                text = open(os.path.join(sa, fn), encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            nm = re.search(r'"name"\s+"([^"]*)"', text)
            name = nm.group(1) if nm else f"App {appid}"
            if re.match(r"(Proton|Steam Linux Runtime|Steamworks Common)", name, re.I):
                continue
            prefix = None
            for base in (lib, root):
                c = os.path.join(base, "steamapps", "compatdata", str(appid))
                if os.path.isdir(os.path.join(c, "pfx")):
                    prefix = c
                    break
            found[appid] = {"appid": appid, "name": name, "prefix": prefix, "library": lib}
    for appid, name in shortcuts(root).items():
        if appid in found:
            continue
        prefix = None
        for lib in libraries(root):
            c = os.path.join(lib, "steamapps", "compatdata", str(appid))
            if os.path.isdir(os.path.join(c, "pfx")):
                prefix = c
                break
        found[appid] = {"appid": appid, "name": name + "  (no Steam)", "prefix": prefix, "library": root}
    return sorted(found.values(), key=lambda g: g["name"].lower())


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def proton_dirs(root):
    """Todos los Proton instalados: {nombre: carpeta}."""
    res = {}
    for base in [os.path.join(root, "compatibilitytools.d"), os.path.join(HOME, ".steam", "root", "compatibilitytools.d")] + \
            [os.path.join(lib, "steamapps", "common") for lib in libraries(root)]:
        try:
            for d in os.listdir(base):
                full = os.path.join(base, d)
                if os.path.isfile(os.path.join(full, "proton")) and d not in res:
                    res[d] = full
        except OSError:
            pass
    return res


def _block(text, key):
    """Contenido de «"key" { ... }» con llaves anidadas (formato VDF de Steam)."""
    m = re.search(r'"%s"\s*\{' % re.escape(key), text)
    if not m:
        return None
    depth, i = 1, m.end()
    while i < len(text) and depth:
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        i += 1
    return text[m.end():i - 1]


def mapped_tool(root, appid):
    """Nombre de la herramienta de compatibilidad que Steam tiene asignada al juego (o la global)."""
    try:
        text = open(os.path.join(root, "config", "config.vdf"), encoding="utf-8", errors="replace").read()
    except OSError:
        return None
    block = _block(text, "CompatToolMapping")
    if not block:
        return None
    for key in (str(appid), "0"):
        sub = _block(block, key)
        if sub:
            e = re.search(r'"name"\s+"([^"]+)"', sub)
            if e:
                return e.group(1)
    return None


def find_proton(root, appid):
    """-> (carpeta, nombre) del Proton que usa el juego; si no se sabe, el más reciente instalado."""
    installed = proton_dirs(root)
    name = mapped_tool(root, appid)
    if name:
        if name in installed:
            return installed[name], name
        want = _norm(name)
        for d, full in installed.items():
            if _norm(d) == want:
                return full, d
        # nombres internos de Steam: proton_9 -> «Proton 9.0», proton_experimental -> «Proton - Experimental»
        if want.startswith("proton"):
            rest = want[len("proton"):]
            for d, full in sorted(installed.items()):
                n = _norm(d)
                if n.startswith("proton") and n[len("proton"):].startswith(rest):
                    return full, d
    if installed:
        d = sorted(installed, key=lambda s: (("experimental" in s.lower()), s), reverse=True)[0]
        return installed[d], d
    return None, name


def download(arch):
    os.makedirs(CACHE, exist_ok=True)
    dst = os.path.join(CACHE, f"vc_redist.{arch}.exe")
    if os.path.isfile(dst) and os.path.getsize(dst) > 1_000_000 and open(dst, "rb").read(2) == b"MZ":
        return dst
    # también vale uno que ya hayas descargado a mano
    for d in ("Downloads", "Descargas"):
        p = os.path.join(HOME, d, f"vc_redist.{arch}.exe")
        if os.path.isfile(p) and os.path.getsize(p) > 1_000_000 and open(p, "rb").read(2) == b"MZ":
            return p
    tmp = dst + ".part"
    req = urllib.request.Request(URLS[arch], headers={"User-Agent": "konkr-toolbox"})
    with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)
    with open(tmp, "rb") as f:
        head = f.read(2)
    if head != b"MZ" or os.path.getsize(tmp) < 1_000_000:
        os.remove(tmp)
        raise RuntimeError("download-invalid")
    os.replace(tmp, dst)
    return dst


def install(appid, arch):
    root = steam_root()
    if not root:
        return out({"ok": False, "error": "no-steam"}, 1)
    g = next((x for x in games(root) if x["appid"] == appid), None)
    if not g:
        return out({"ok": False, "error": "no-game"}, 1)
    if not g["prefix"]:
        return out({"ok": False, "error": "no-prefix"}, 1)
    proton, pname = find_proton(root, appid)
    if not proton:
        return out({"ok": False, "error": "no-proton"}, 1)
    try:
        exe = download(arch)
    except Exception as e:  # noqa
        return out({"ok": False, "error": "download", "detail": str(e)[:200]}, 1)
    env = dict(os.environ)
    env.update({"STEAM_COMPAT_DATA_PATH": g["prefix"], "STEAM_COMPAT_CLIENT_INSTALL_PATH": root,
                "SteamAppId": str(appid), "SteamGameId": str(appid), "WINEDEBUG": "-all"})
    env.setdefault("DISPLAY", ":0")
    cmd = [os.path.join(proton, "proton"), "run", exe, "/install", "/quiet", "/norestart"]
    os.makedirs(CACHE, exist_ok=True)
    t0 = time.time()
    try:
        with open(LOG, "w", encoding="utf-8") as lf:
            lf.write(f"{time.strftime('%F %T')} {' '.join(cmd)}\n")
            lf.flush()
            r = subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT, env=env, cwd=os.path.dirname(exe), timeout=420)
        rc = r.returncode
    except subprocess.TimeoutExpired:
        return out({"ok": False, "error": "timeout", "proton": pname, "log": LOG}, 1)
    except OSError as e:
        return out({"ok": False, "error": "exec", "detail": str(e)[:200], "proton": pname, "log": LOG}, 1)
    tail = ""
    try:
        tail = open(LOG, encoding="utf-8", errors="replace").read()[-400:]
    except OSError:
        pass
    status = OK_CODES.get(rc)
    return out({"ok": status is not None, "status": status or "failed", "code": rc, "proton": pname,
                "seconds": round(time.time() - t0), "log": LOG, "tail": "" if status else tail})


def main(argv):
    try:
        cmd = argv[0] if argv else ""
        if cmd == "games":
            root = steam_root()
            if not root:
                return out({"ok": False, "error": "no-steam"}, 1)
            lst = []
            for g in games(root):
                if not g["prefix"]:
                    continue
                _p, pname = find_proton(root, g["appid"])
                lst.append({"appid": g["appid"], "name": g["name"], "proton": pname})
            return out({"ok": True, "games": lst})
        if cmd == "install" and len(argv) >= 3 and argv[2] in URLS:
            return install(int(argv[1]), argv[2])
        return out({"ok": False, "error": "bad-command"}, 1)
    except Exception as e:  # noqa — el plugin necesita siempre una respuesta JSON
        return out({"ok": False, "error": f"{type(e).__name__}: {e}"}, 1)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
