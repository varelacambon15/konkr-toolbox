"""Konkr Toolbox: backend del plugin de Decky.

Corre como root (flag "root" en plugin.json) porque activar o desactivar SSH lo necesita.
Konkr Tweaks, en cambio, se ejecuta siempre como el usuario normal (runuser), para que sus
ajustes y los archivos de los juegos sigan siendo suyos.
"""
import asyncio
import json
import os
import re
import shutil
import socket
import subprocess

import decky

KT_APP = os.path.join(".local", "share", "konkr-tweaks", "app")
PY = "/usr/bin/python3" if os.path.exists("/usr/bin/python3") else "python3"
SSH_UNIT = "sshd"


def _user():
    return getattr(decky, "DECKY_USER", None) or os.environ.get("DECKY_USER", "steamos")


def _home():
    return getattr(decky, "DECKY_USER_HOME", None) or os.environ.get("DECKY_USER_HOME", f"/home/{_user()}")


def _env(as_user):
    """Entorno limpio: el LD_LIBRARY_PATH de Decky rompe a veces los programas del sistema."""
    env = {k: v for k, v in os.environ.items() if k not in ("LD_LIBRARY_PATH", "PYTHONPATH", "PYTHONHOME")}
    env["PATH"] = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    env.setdefault("LANG", "C.UTF-8")
    if as_user:
        env["HOME"] = _home()
        env["USER"] = env["LOGNAME"] = _user()
        try:
            import pwd
            env["XDG_RUNTIME_DIR"] = f"/run/user/{pwd.getpwnam(_user()).pw_uid}"
        except (KeyError, ImportError):
            pass
    return env


async def _run(cmd, timeout=30, as_user=False, cwd=None):
    """Ejecuta un programa sin bloquear Decky. Usa subprocess en un hilo (como Handheld
    Control del port): Decky corre bajo Box64 y así se evita depender del vigilante de
    procesos de asyncio."""
    if as_user and os.geteuid() == 0:
        cmd = (["runuser", "-u", _user(), "--"] if shutil.which("runuser") else ["sudo", "-u", _user()]) + cmd
    try:
        r = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, timeout=timeout,
                                    env=_env(as_user), cwd=cwd)
        return r.returncode, r.stdout.decode(errors="replace").strip(), r.stderr.decode(errors="replace").strip()
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
    except (OSError, ValueError) as e:
        return 127, "", str(e)


# ------------------------------------------------------------------ Konkr Tweaks

async def _kt(*args, timeout=60):
    app = os.path.join(_home(), KT_APP)
    if not os.path.isdir(os.path.join(app, "konkr_tweaks")):
        return {"ok": False, "error": "not-installed"}
    rc, out, err = await _run([PY, "-m", "konkr_tweaks.cli", *args], timeout=timeout, as_user=True, cwd=app)
    line = out.splitlines()[-1] if out else ""
    try:
        data = json.loads(line)
    except ValueError:
        decky.logger.error(f"konkr-tweaks {args}: rc={rc} out={out[-300:]} err={err[-500:]}")
        old = "unwrap-all" in out   # versión anterior a la 0.3.0: no conoce las órdenes json-*
        return {"ok": False, "error": "old-version" if old else (err[-200:] or out[-200:] or f"rc={rc}")}
    if not data.get("ok"):
        decky.logger.warning(f"konkr-tweaks {args}: {data}")
    return data


# ------------------------------------------------------------------ Dependencias

async def _deps(*args, timeout=60):
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "py_modules", "ktb_deps.py")
    rc, out, err = await _run([PY, script, *args], timeout=timeout, as_user=True)
    line = out.splitlines()[-1] if out else ""
    try:
        data = json.loads(line)
    except ValueError:
        decky.logger.error(f"deps {args}: rc={rc} out={out[-300:]} err={err[-500:]}")
        return {"ok": False, "error": err[-200:] or out[-200:] or f"rc={rc}"}
    if not data.get("ok"):
        decky.logger.warning(f"deps {args}: {data}")
    return data


# ------------------------------------------------------------------ Mapeos de mando

async def _maps(*args, timeout=60):
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "py_modules", "ktb_maps.py")
    rc, out, err = await _run([PY, script, *args], timeout=timeout, as_user=True)
    line = out.splitlines()[-1] if out else ""
    try:
        return json.loads(line)
    except ValueError:
        decky.logger.error(f"maps {args}: rc={rc} out={out[-300:]} err={err[-500:]}")
        return {"ok": False, "error": err[-200:] or out[-200:] or f"rc={rc}"}


# ------------------------------------------------------------------ SSH

async def _systemctl(*args):
    rc, out, _err = await _run(["systemctl", *args, SSH_UNIT], timeout=20)
    return rc, out


async def _ssh_port():
    rc, out, _ = await _run(["sshd", "-T"], timeout=10)
    if rc == 0:
        ports = [ln.split()[1] for ln in out.splitlines() if ln.startswith("port ")]
        if ports:
            return ", ".join(ports)
    port = "22"
    for path in ["/etc/ssh/sshd_config"] + sorted(
            os.path.join("/etc/ssh/sshd_config.d", f) for f in (os.listdir("/etc/ssh/sshd_config.d")
                                                               if os.path.isdir("/etc/ssh/sshd_config.d") else [])):
        try:
            for ln in open(path, encoding="utf-8", errors="replace"):
                m = re.match(r"\s*Port\s+(\d+)", ln, re.I)
                if m:
                    port = m.group(1)
        except OSError:
            pass
    return port


async def _addresses():
    rc, out, _ = await _run(["ip", "-4", "-o", "addr", "show", "scope", "global"], timeout=10)
    addrs = []
    if rc == 0:
        for ln in out.splitlines():
            m = re.match(r"\d+:\s+(\S+)\s+inet\s+([\d.]+)/", ln)
            if m:
                addrs.append({"iface": m.group(1), "ip": m.group(2)})
    return addrs


async def _wifi():
    if not shutil.which("nmcli"):
        return None
    rc, out, _ = await _run(["nmcli", "-t", "-f", "ACTIVE,SSID", "dev", "wifi"], timeout=10)
    if rc == 0:
        for ln in out.splitlines():
            if ln.startswith("yes:") or ln.startswith("sí:"):
                return ln.split(":", 1)[1].replace("\\:", ":") or None
    return None


async def _password_set():
    rc, out, _ = await _run(["passwd", "-S", _user()], timeout=10)
    if rc != 0 or not out:
        return None
    parts = out.split()
    return parts[1] == "P" if len(parts) > 1 else None


class Plugin:
    # ---------- Konkr Tweaks
    async def kt_games(self):
        return await _kt("json-games")

    async def kt_status(self, appid):
        return await _kt("json-status", str(int(appid)))

    async def kt_apply(self, appid, mode, running=False):
        args = ["json-apply", str(int(appid)), str(mode)] + (["--running"] if running else [])
        return await _kt(*args, timeout=120)

    async def kt_restore(self, appid):
        return await _kt("json-restore", str(int(appid)), timeout=120)

    # ---------- Dependencias
    async def deps_games(self):
        return await _deps("games")

    async def deps_install(self, appid, dep, variant):
        return await _deps("install", str(int(appid)), str(dep), str(variant), timeout=500)

    # ---------- Mapeos de mando
    async def maps_list(self):
        return await _maps("list", timeout=90)

    async def maps_install(self, path):
        return await _maps("install", str(path))

    async def maps_remove(self, name):
        return await _maps("remove", str(name))

    # ---------- SSH
    async def ssh_status(self):
        rc_a, active = await _systemctl("is-active")
        _rc, enabled = await _systemctl("is-enabled")
        installed = bool(shutil.which("sshd")) or os.path.exists("/usr/lib/systemd/system/sshd.service")
        return {
            "installed": installed,
            "active": rc_a == 0 and active == "active",
            "enabled": enabled == "enabled",
            "state": active,
            "port": await _ssh_port(),
            "addresses": await _addresses(),
            "wifi": await _wifi(),
            "hostname": socket.gethostname(),
            "user": _user(),
            "password": await _password_set(),
        }

    async def ssh_set(self, on):
        if on:
            rc, out = await _systemctl("enable", "--now")
        else:
            rc, out = await _systemctl("disable", "--now")
        decky.logger.info(f"ssh {'on' if on else 'off'}: rc={rc} {out}")
        st = await self.ssh_status()
        st["ok"] = rc == 0
        return st

    # ---------- ciclo de vida
    async def _main(self):
        decky.logger.info(f"Konkr Toolbox listo (usuario {_user()}, home {_home()})")
        # Si una actualización de Steam borró las plantillas de mando, se vuelven a poner
        r = await _maps("restore")
        if r.get("restored"):
            decky.logger.info(f"plantillas de mando restauradas: {r['restored']}")

    async def _unload(self):
        pass

    async def _uninstall(self):
        pass
