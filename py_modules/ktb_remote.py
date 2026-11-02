#!/usr/bin/env python3
"""Konkr Toolbox: control remoto desde el navegador (VNC local + noVNC).

Se ejecuta SIEMPRE como el usuario normal (no como root) y solo con la biblioteca estándar.

Cómo funciona:
  - x11vnc comparte la pantalla X (en Modo Juego, la de gamescope) y escucha SOLO en 127.0.0.1.
  - websockify (incluido en py_modules/vendor) sirve la página de static/ y la conecta con x11vnc.
  - Cada activación crea una contraseña nueva y se apaga sola pasado un tiempo.

Órdenes (cada una imprime una línea JSON):
  diag                       qué hay disponible en este equipo (no cambia nada)
  status                     estado actual
  start [minutos] [:display] enciende (por defecto 30 minutos)
  stop                       apaga y borra la contraseña
  watch <epoch>              uso interno: apaga cuando llega la hora
"""
import json
import os
import secrets
import shutil
import signal
import subprocess
import sys
import time
import socket

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
STATIC = os.path.join(PLUGIN, "static")
VENDOR = os.path.join(HERE, "vendor")
HOME = os.path.expanduser("~")
STATE_DIR = os.path.join(HOME, ".cache", "konkr-toolbox")
STATE = os.path.join(STATE_DIR, "remote.json")
RFBAUTH = os.path.join(STATE_DIR, "remote.rfbauth")
LOG = os.path.join(STATE_DIR, "remote.log")
VNC_PORT = 5901
WEB_PORT = 6080
DEFAULT_MINUTES = 30
MAX_MINUTES = 240
# Sin 0/O/1/l/I para que sea fácil de leer y teclear. VNC solo usa los 8 primeros caracteres.
ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def out(data):
    print(json.dumps(data, ensure_ascii=False))


def alive(pid):
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    # Un proceso zombi cuenta como muerto
    try:
        with open(f"/proc/{pid}/stat") as f:
            return f.read().rsplit(")", 1)[1].split()[0] != "Z"
    except (OSError, IndexError):
        return True


def port_open(port, host="127.0.0.1"):
    s = socket.socket()
    s.settimeout(0.5)
    try:
        s.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def read_state():
    try:
        with open(STATE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def displays():
    """Pantallas X disponibles (por los sockets de /tmp/.X11-unix)."""
    found = []
    try:
        for n in sorted(os.listdir("/tmp/.X11-unix")):
            if n.startswith("X") and n[1:].isdigit():
                found.append(":" + n[1:])
    except OSError:
        pass
    return found


def process_names():
    names = set()
    try:
        for pid in os.listdir("/proc"):
            if pid.isdigit():
                try:
                    with open(f"/proc/{pid}/comm") as f:
                        names.add(f.read().strip())
                except OSError:
                    pass
    except OSError:
        pass
    return names


def have_web():
    return (os.path.isfile(os.path.join(STATIC, "index.html"))
            and os.path.isfile(os.path.join(VENDOR, "websockify", "__init__.py")))


def tail(path, n=6):
    try:
        with open(path, errors="replace") as f:
            return " | ".join(l.strip() for l in f.read().splitlines()[-n:] if l.strip())
    except OSError:
        return ""


def kill_group(pid):
    if not pid:
        return
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pid, sig)
        except (ProcessLookupError, PermissionError):
            try:
                os.kill(pid, sig)
            except OSError:
                pass
        for _ in range(20):
            if not alive(pid):
                return
            time.sleep(0.1)


def cmd_diag():
    names = process_names()
    return {
        "ok": True,
        "displays": displays(),
        "gamescope": "gamescope" in names or "gamescope-wl" in names,
        "x11vnc": shutil.which("x11vnc"),
        "web": have_web(),
        "session": os.environ.get("XDG_SESSION_TYPE", ""),
        "state": status_data(),
    }


def status_data():
    st = read_state()
    if not st:
        return {"active": False}
    left = int(st.get("expires", 0) - time.time())
    ok = (alive(st.get("vnc_pid")) and alive(st.get("web_pid")) and left > 0)
    if not ok:
        return {"active": False, "stale": True}
    return {"active": True, "password": st.get("password"), "web_port": st.get("web_port"),
            "display": st.get("display"), "seconds_left": left}


def cmd_status():
    d = status_data()
    d["ok"] = True
    if d.get("stale"):
        cleanup()   # lo que quedara a medias se limpia
        d.pop("stale", None)
    return d


def cleanup():
    st = read_state() or {}
    kill_group(st.get("web_pid"))
    kill_group(st.get("vnc_pid"))
    if st.get("watch_pid") != os.getpid():   # el vigilante no se mata a sí mismo antes de limpiar
        kill_group(st.get("watch_pid"))
    for p in (STATE, RFBAUTH):
        try:
            os.remove(p)
        except OSError:
            pass


def cmd_stop():
    cleanup()
    return {"ok": True, "active": False}


def cmd_start(minutes, display):
    cur = status_data()
    if cur.get("active"):
        cur["ok"] = True
        return cur
    cleanup()
    x11vnc = shutil.which("x11vnc")
    if not x11vnc:
        return {"ok": False, "error": "no-x11vnc"}
    if not have_web():
        return {"ok": False, "error": "no-web"}
    avail = displays()
    if not display:
        display = ":0" if ":0" in avail else (avail[0] if avail else "")
    if not display or display not in avail:
        return {"ok": False, "error": "no-display"}
    minutes = max(1, min(int(minutes or DEFAULT_MINUTES), MAX_MINUTES))

    os.makedirs(STATE_DIR, mode=0o700, exist_ok=True)
    os.chmod(STATE_DIR, 0o700)
    password = "".join(secrets.choice(ALPHABET) for _ in range(8))
    r = subprocess.run([x11vnc, "-storepasswd", password, RFBAUTH], capture_output=True)
    if r.returncode != 0 or not os.path.isfile(RFBAUTH):
        return {"ok": False, "error": "storepasswd", "detail": r.stderr.decode(errors="replace")[-200:]}
    os.chmod(RFBAUTH, 0o600)

    logf = open(LOG, "w")
    os.chmod(LOG, 0o600)
    env = dict(os.environ)
    env["PYTHONPATH"] = VENDOR

    # x11vnc necesita acceso a la pantalla X: primero busca la autorización sola ("guess") y, si no
    # hay, prueba sin ella (las pantallas de gamescope y las virtuales suelen no pedirla).
    vnc = None
    for auth in (["-auth", "guess"], []):
        vnc = subprocess.Popen(
            [x11vnc, "-display", display, *auth, "-rfbport", str(VNC_PORT), "-localhost",
             "-rfbauth", RFBAUTH, "-forever", "-shared", "-noxdamage", "-noipv6", "-wait", "20", "-defer", "20"],
            stdout=logf, stderr=logf, stdin=subprocess.DEVNULL, start_new_session=True)
        for _ in range(40):   # hasta 4 s
            if not alive(vnc.pid) or port_open(VNC_PORT):
                break
            time.sleep(0.1)
        if alive(vnc.pid) and port_open(VNC_PORT):
            break
        kill_group(vnc.pid)
    web = subprocess.Popen(
        [sys.executable, "-m", "websockify", "--web", STATIC, f"0.0.0.0:{WEB_PORT}", f"127.0.0.1:{VNC_PORT}"],
        stdout=logf, stderr=logf, stdin=subprocess.DEVNULL, start_new_session=True, env=env)

    expires = time.time() + minutes * 60
    state = {"vnc_pid": vnc.pid, "web_pid": web.pid, "password": password, "display": display,
             "web_port": WEB_PORT, "expires": expires}

    for _ in range(60):   # hasta 6 s
        if not alive(vnc.pid) or not alive(web.pid):
            break
        if port_open(VNC_PORT) and port_open(WEB_PORT):
            break
        time.sleep(0.1)
    if not (alive(vnc.pid) and alive(web.pid) and port_open(VNC_PORT) and port_open(WEB_PORT)):
        detail = tail(LOG)
        state["watch_pid"] = None
        with open(STATE, "w") as f:
            json.dump(state, f)
        cleanup()
        return {"ok": False, "error": "no-start", "detail": detail[-400:]}

    watcher = subprocess.Popen([sys.executable, os.path.abspath(__file__), "watch", str(expires)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                               start_new_session=True)
    state["watch_pid"] = watcher.pid
    fd = os.open(STATE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(state, f)
    d = status_data()
    d["ok"] = True
    return d


def cmd_watch(expires):
    """Se queda esperando y apaga todo cuando llega la hora o si alguien ya lo apagó."""
    time.sleep(3)   # da tiempo a que start escriba el estado
    while time.time() < expires:
        st = read_state()
        if not st or st.get("watch_pid") not in (None, os.getpid()):
            return
        time.sleep(5)
    cleanup()


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "status"
    try:
        if cmd == "diag":
            out(cmd_diag())
        elif cmd == "status":
            out(cmd_status())
        elif cmd == "start":
            minutes = int(argv[2]) if len(argv) > 2 and argv[2].isdigit() else DEFAULT_MINUTES
            display = argv[3] if len(argv) > 3 else ""
            out(cmd_start(minutes, display))
        elif cmd == "stop":
            out(cmd_stop())
        elif cmd == "watch":
            cmd_watch(float(argv[2]))
        else:
            out({"ok": False, "error": "unknown-command"})
    except Exception as e:   # nunca dejar a Decky sin respuesta JSON
        out({"ok": False, "error": f"{type(e).__name__}: {e}"})


if __name__ == "__main__":
    main(sys.argv)
