#!/usr/bin/env python3
"""Konkr Toolbox: instala y controla Konkr Mod Manager (Skyrim SE, Fallout 4, Oblivion).

Se ejecuta SIEMPRE como el usuario normal (no como root) y solo con la biblioteca estándar.
Todo va a la carpeta del usuario; no toca el sistema ni Steam.

Órdenes (cada una imprime una línea JSON):
  status [ip]     estado: instalado, servicio, PIN, dirección y código QR (SVG) para el móvil
  install         instala o actualiza desde la copia incluida en el plugin
  uninstall       quita el programa (conserva mods y ajustes)
  service on|off  enciende o apaga el servidor para el móvil
  newpin          genera un PIN nuevo y desempareja los móviles
"""
import base64
import json
import os
import re
import secrets
import signal
import socket
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
SRC = os.path.join(PLUGIN, "modmanager")
HOME = os.path.expanduser("~")
DATA = os.path.join(HOME, ".local", "share", "konkr-modmanager")
APP = os.path.join(DATA, "app")
CONFIG = os.path.join(DATA, "config.json")
UNIT = "konkr-modmanager-server.service"
DEFAULT_PORT = 8765


def out(data):
    print(json.dumps(data, ensure_ascii=False))


def version_of(folder):
    try:
        with open(os.path.join(folder, "konkr_mm", "__init__.py"), encoding="utf-8") as f:
            m = re.search(r'__version__\s*=\s*"([^"]+)"', f.read())
            return m.group(1) if m else None
    except OSError:
        return None


def read_config():
    try:
        with open(CONFIG, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def write_config(cfg):
    os.makedirs(DATA, exist_ok=True)
    tmp = CONFIG + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CONFIG)


def systemctl(*args):
    try:
        r = subprocess.run(["systemctl", "--user", *args], capture_output=True, timeout=30)
        return r.returncode, r.stdout.decode(errors="replace").strip(), r.stderr.decode(errors="replace").strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return 127, "", str(e)


def port_open(port):
    s = socket.socket()
    s.settimeout(0.5)
    try:
        s.connect(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def server_pids():
    """Procesos del servidor (por si se lanzó sin systemd)."""
    pids = []
    for pid in os.listdir("/proc"):
        if pid.isdigit() and int(pid) != os.getpid():
            try:
                with open(f"/proc/{pid}/cmdline", "rb") as f:
                    parts = f.read().split(b"\0")
            except OSError:
                continue
            if b"konkr_mm" in parts and b"--server" in parts:
                pids.append(int(pid))
    return pids


def spawn_server():
    """Plan B si systemd de usuario no está disponible: servidor suelto en segundo plano."""
    if server_pids():
        return
    subprocess.Popen([sys.executable, "-m", "konkr_mm", "--server"], cwd=APP,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                     start_new_session=True)
    time.sleep(1.5)


def kill_server():
    for pid in server_pids():
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    time.sleep(0.5)


def qr_svg_uri(text):
    """Código QR como imagen SVG lista para un <img src="...">."""
    try:
        sys.path.insert(0, os.path.join(SRC))
        from konkr_mm.qrcodegen import QrCode
    except Exception:
        return None
    qr = QrCode.encode_text(text, QrCode.Ecc.MEDIUM)
    n = qr.get_size()
    b = 3
    cells = "".join(f"M{x + b},{y + b}h1v1h-1z" for y in range(n) for x in range(n) if qr.get_module(x, y))
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n + 2 * b} {n + 2 * b}" '
           f'shape-rendering="crispEdges"><rect width="100%" height="100%" fill="#fff"/>'
           f'<path d="{cells}" fill="#000"/></svg>')
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


def cmd_status(ip=""):
    cfg = read_config()
    comp = cfg.get("companion", {})
    installed = os.path.isfile(os.path.join(APP, "konkr_mm", "__main__.py"))
    rc, state, _ = systemctl("is-active", UNIT)
    port0 = read_config().get("companion", {}).get("port", DEFAULT_PORT)
    active = (rc == 0 and state == "active") or port_open(port0)
    rc_e, en, _ = systemctl("is-enabled", UNIT)
    port = comp.get("port", DEFAULT_PORT)
    d = {
        "ok": True,
        "installed": installed,
        "version": version_of(APP) if installed else None,
        "bundled": version_of(SRC),
        "service": active,
        "enabled": rc_e == 0 and en == "enabled",
        "port": port,
        "pin": comp.get("pin") if installed else None,
        "paired": len(comp.get("tokens", [])),
        "nexus_key": bool(cfg.get("api_key")),
        "unit_state": state,
    }
    if installed and active and ip and comp.get("pin"):
        d["url"] = f"http://{ip}:{port}/"
        d["qr"] = qr_svg_uri(f"http://{ip}:{port}/#pin={comp['pin']}")
    return d


def cmd_install():
    if not os.path.isfile(os.path.join(SRC, "install.sh")):
        return {"ok": False, "error": "no-bundle"}
    r = subprocess.run(["bash", os.path.join(SRC, "install.sh")], capture_output=True, timeout=180,
                       cwd=SRC, env={**os.environ, "LANG": "es_ES.UTF-8"})
    if r.returncode != 0:
        return {"ok": False, "error": "install-failed",
                "detail": (r.stdout + r.stderr).decode(errors="replace")[-400:]}
    # el servicio se activa en install.sh; si no pudo, se intenta una vez más
    rc, state, _ = systemctl("is-active", UNIT)
    if rc != 0:
        systemctl("enable", "--now", UNIT)
        if systemctl("is-active", UNIT)[0] != 0:
            spawn_server()
    return cmd_status()


def cmd_uninstall():
    sh = os.path.join(SRC, "uninstall.sh")
    if not os.path.isfile(sh):
        return {"ok": False, "error": "no-bundle"}
    kill_server()
    subprocess.run(["bash", sh], capture_output=True, timeout=60, env={**os.environ, "LANG": "es_ES.UTF-8"})
    return cmd_status()


def cmd_service(on):
    if not os.path.isfile(os.path.join(APP, "konkr_mm", "__main__.py")):
        return {"ok": False, "error": "not-installed"}
    rc, _o, err = systemctl("enable", "--now", UNIT) if on else systemctl("disable", "--now", UNIT)
    if on:
        if rc != 0 or not port_open(read_config().get("companion", {}).get("port", DEFAULT_PORT)):
            spawn_server()
    else:
        kill_server()
    d = cmd_status()
    if (on and not d["service"]) or (not on and d["service"]):
        d["ok"] = False
        d["error"] = "service"
        d["detail"] = err[-300:]
    return d


def cmd_newpin():
    cfg = read_config()
    comp = cfg.setdefault("companion", {})
    comp["pin"] = f"{secrets.randbelow(10 ** 6):06d}"
    comp["tokens"] = []
    write_config(cfg)
    # el servidor lee el PIN al arrancar: se reinicia para que use el nuevo
    if systemctl("restart", UNIT)[0] != 0:
        kill_server()
        spawn_server()
    return cmd_status()


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "status"
    try:
        if cmd == "status":
            out(cmd_status(argv[2] if len(argv) > 2 else ""))
        elif cmd == "install":
            out(cmd_install())
        elif cmd == "uninstall":
            out(cmd_uninstall())
        elif cmd == "service":
            out(cmd_service(len(argv) > 2 and argv[2] == "on"))
        elif cmd == "newpin":
            out(cmd_newpin())
        else:
            out({"ok": False, "error": "unknown-command"})
    except Exception as e:   # nunca dejar a Decky sin respuesta JSON
        out({"ok": False, "error": f"{type(e).__name__}: {e}"})


if __name__ == "__main__":
    main(sys.argv)
