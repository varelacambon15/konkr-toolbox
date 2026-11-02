"""Servidor del companion móvil: sirve la app web y una API JSON en la red local.
Acceso protegido con un PIN de 6 cifras que se muestra en la Konkr."""
import json
import os
import secrets
import socket
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import __version__, bbcode, core, nexus
from .games import GAMES, NEXUS_TO_GAME
from .jobs import JobQueue
from .i18n import _
from . import i18n

DEFAULT_PORT = 8765
WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/manifest.json": ("manifest.json", "application/manifest+json"),
    "/icon.svg": ("icon.svg", "image/svg+xml"),
    "/icon-192.png": ("icon-192.png", "image/png"),
    "/icon-512.png": ("icon-512.png", "image/png"),
}


class ApiError(Exception):
    def __init__(self, status, msg):
        super().__init__(msg)
        self.status = status


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))  # no envía nada; solo elige la interfaz de salida
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def _installed_ts(mod):
    if mod.get("installed_ts"):
        return mod["installed_ts"]
    try:
        return int(time.mktime(time.strptime(mod.get("installed", ""), "%Y-%m-%d %H:%M")))
    except ValueError:
        return 0


class Companion:
    def __init__(self, mgr, port=None):
        self.mgr = mgr
        cfg = mgr.config.setdefault("companion", {})
        cfg.setdefault("enabled", True)
        cfg.setdefault("port", DEFAULT_PORT)
        cfg.setdefault("tokens", [])
        cfg.setdefault("show_adult", False)
        if not cfg.get("pin"):
            cfg["pin"] = f"{secrets.randbelow(10**6):06d}"
        mgr.save_config()
        self.cfg = cfg
        self.port = port or cfg["port"]
        self.queue = JobQueue(mgr)
        self.httpd = None
        self._browser = None
        self._fails = []
        self.account = None  # resultado de validate() cacheado

    # ---- ciclo de vida -----------------------------------------------------
    def start(self):
        handler = type("H", (Handler,), {"comp": self})
        self.httpd = ThreadingHTTPServer(("0.0.0.0", self.port), handler)
        self.httpd.daemon_threads = True
        threading.Thread(target=self.httpd.serve_forever, daemon=True, name="kmm-http").start()
        self.mgr.log(_("Companion móvil activo en {url}", url=self.url))

    def stop(self):
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None

    @property
    def running(self):
        return self.httpd is not None

    @property
    def url(self):
        return f"http://{lan_ip()}:{self.port}"

    @property
    def pin(self):
        return self.cfg["pin"]

    def new_pin(self):
        self.cfg["pin"] = f"{secrets.randbelow(10**6):06d}"
        self.cfg["tokens"] = []  # desconecta los móviles emparejados
        self.mgr.save_config()
        return self.cfg["pin"]

    @property
    def browser(self):
        if self._browser is None or self._browser.api_key != self.mgr.api_key:
            self._browser = nexus.Browser(self.mgr.api_key)
        return self._browser

    # ---- autenticación -------------------------------------------------------
    def login(self, pin):
        now = time.time()
        self._fails = [t for t in self._fails if now - t < 600]
        if len(self._fails) >= 8:
            raise ApiError(429, _("Demasiados intentos. Espera 10 minutos."))
        if not secrets.compare_digest(str(pin).strip(), self.pin):
            self._fails.append(now)
            raise ApiError(403, _("PIN incorrecto."))
        tok = secrets.token_hex(24)
        self.cfg["tokens"] = (self.cfg["tokens"] + [tok])[-10:]
        self.mgr.save_config()
        return tok

    def check_token(self, tok):
        return bool(tok) and any(secrets.compare_digest(tok, t) for t in self.cfg["tokens"])

    # ---- utilidades ----------------------------------------------------------
    def ctx(self, key):
        if key not in GAMES:
            raise ApiError(404, _("Juego desconocido."))
        return self.mgr.game(key)

    def locked_call(self, fn, *a, **k):
        if not self.mgr.lock.acquire(timeout=3):
            raise ApiError(409, _("La consola está ocupada (aplicando o instalando). Prueba en un momento."))
        try:
            return fn(*a, **k)
        finally:
            self.mgr.lock.release()

    def installed_map(self, ctx):
        out = {}
        for m in ctx.mods:
            src = m.get("source") or {}
            if src.get("type") == "nexus":
                out.setdefault(int(src.get("mod_id", 0)), []).append(
                    {"id": m["id"], "name": m["name"], "version": m.get("version", ""),
                     "file_id": src.get("file_id"), "enabled": m["enabled"]})
        return out

    # ---- tareas ----------------------------------------------------------------
    def submit_install(self, game, mod_id, file_id, key=None, expires=None, replace_id=None):
        ctx = self.ctx(game)
        if not ctx.found:
            raise ApiError(400, _("No se encuentra el juego en la consola."))
        if not self.mgr.api_key:
            raise ApiError(400, _("Falta la clave de API de Nexus en la consola."))
        domain = GAMES[game]["nexus"]
        detail = self.browser.mod_detail(domain, mod_id)
        f = next((x for x in detail["files"] if x["file_id"] == file_id), None)
        if not f:
            raise ApiError(404, _("Ese archivo ya no existe en Nexus."))
        name = nexus.nice_name(detail["name"], f)
        api_key = self.mgr.api_key
        mgr = self.mgr

        def run(job):
            api = nexus.Nexus(api_key)
            job.set_progress(0, _("Pidiendo el enlace a Nexus…"))
            url = api.download_url(domain, mod_id, file_id, key, expires)
            total = (f["size_kb"] or 0) * 1024

            def prog(done, tot):
                tot = tot or total
                job.set_progress(0.85 * done / tot if tot else None,
                                 f"Descargando {done / 1048576:.1f} / {tot / 1048576:.1f} MB")
            path = api.download(url, ctx.downloads, f["file_name"], prog, lambda: job.cancelled)

            def iprog(frac, text):
                job.set_progress(None if frac is None else 0.85 + 0.15 * frac, text)
            mod = ctx.install_archive(path, name=name, version=f["version"],
                                      source={"type": "nexus", "domain": domain, "mod_id": mod_id,
                                              "file_id": file_id},
                                      chooser=job.ask_choice, progress=iprog,
                                      delete_archive=mgr.config.get("delete_archives", True),
                                      replace_id=replace_id)
            if not mod:
                return None
            job.text = _("Instalado. Pulsa «Aplicar» para ponerlo en el juego.")
            return {"mod": mod["id"]}
        title = _("Actualizar: {name}", name=name) if replace_id else name
        return self.queue.submit(title, game, run)

    def submit_apply(self, game):
        ctx = self.ctx(game)
        if core.game_running(game):
            raise ApiError(409, _("{game} está abierto en la consola. Ciérralo primero.", game=GAMES[game]["name"]))

        def run(job):
            def prog(frac, text):  # aplicar no se puede cancelar a medias
                if frac is not None:
                    job.progress = frac
                if text:
                    job.text = text
            stats = ctx.apply(prog)
            job.text = _("Hecho.") + " " + core.stats_text(stats)
            return stats
        return self.queue.submit(_("Aplicar mods a {game}", game=GAMES[game]["name"]), game, run, kind="apply")

    # ---- actualizaciones ---------------------------------------------------------
    def check_updates(self, game):
        ctx = self.ctx(game)
        domain = GAMES[game]["nexus"]
        upd = self.browser.updated_since(domain, "1m")
        out = []
        for m in ctx.mods:
            src = m.get("source") or {}
            if src.get("type") != "nexus":
                continue
            ts = upd.get(int(src.get("mod_id", 0)))
            if ts and ts > _installed_ts(m) + 60:
                out.append({"id": m["id"], "name": m["name"], "mod_id": src["mod_id"], "updated": ts})
        return out


class Handler(BaseHTTPRequestHandler):
    comp = None  # se fija al crear el servidor
    server_version = "KonkrModManager"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # silencio
        pass

    # ---- respuesta ---------------------------------------------------------
    def _send(self, status, body, ctype="application/json; charset=utf-8", extra=None):
        if not isinstance(body, (bytes, bytearray)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 1_000_000:
            raise ApiError(413, _("Petición demasiado grande."))
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except ValueError:
            raise ApiError(400, _("JSON no válido."))

    def do_GET(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")

    def _route(self, method):
        u = urllib.parse.urlparse(self.path)
        path, q = u.path, {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        try:
            if method == "GET" and path in STATIC:
                fname, ctype = STATIC[path]
                with open(os.path.join(WEB_DIR, fname), "rb") as f:
                    data = f.read()
                extra = {"Content-Security-Policy":
                         "default-src 'self'; img-src 'self' https: data:; style-src 'self' 'unsafe-inline'; "
                         "script-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'"} \
                    if fname == "index.html" else None
                return self._send(200, data, ctype, extra)
            if not path.startswith("/api/"):
                raise ApiError(404, _("No encontrado."))
            c = self.comp
            if path == "/api/ping":
                return self._send(200, {"app": "konkr-modmanager", "version": __version__,
                                        "host": socket.gethostname()})
            if path == "/api/i18n":
                return self._send(200, {"language": i18n.current(), "catalog": i18n.catalog()})
            if path == "/api/login" and method == "POST":
                return self._send(200, {"token": c.login(self._body().get("pin", ""))})
            if not c.check_token(self.headers.get("X-KMM-Token", "")):
                raise ApiError(401, _("Hace falta emparejar con el PIN."))
            data = self._body() if method == "POST" else {}
            return self._send(200, self.api(method, path, q, data))
        except ApiError as e:
            self._send(e.status, {"error": str(e)})
        except (core.ModError, nexus.NexusError) as e:
            self._send(400, {"error": str(e)})
        except FileNotFoundError:
            self._send(404, {"error": "No encontrado."})
        except Exception as e:  # noqa
            import traceback
            self.comp.mgr.log(_("Error del companion:") + " " + traceback.format_exc())
            self._send(500, {"error": _("Error interno: {error}", error=e)})

    # ---- API ------------------------------------------------------------------
    def api(self, method, path, q, data):
        c = self.comp
        mgr = c.mgr
        parts = path.strip("/").split("/")[1:]  # sin "api"

        if parts == ["overview"]:
            games = []
            for k, g in GAMES.items():
                ctx = mgr.game(k)
                games.append({"key": k, "name": g["name"], "found": ctx.found, "mods": len(ctx.mods),
                              "dirty": ctx.state.get("dirty", False)})
            return {"games": games, "last_game": mgr.config.get("last_game", "skyrimse"),
                    "nexus_key": bool(mgr.api_key), "account": c.account,
                    "host": socket.gethostname(), "version": __version__,
                    "show_adult": c.cfg.get("show_adult", False),
                    "language": i18n.current(), "language_pref": mgr.config.get("language", "auto"),
                    "languages": i18n.available(),
                    "active_jobs": len(c.queue.active())}

        if parts == ["account"]:
            if not mgr.api_key:
                return {"ok": False}
            d = nexus.Nexus(mgr.api_key).validate()
            c.account = {"name": d.get("name"), "premium": d.get("premium")}
            return {"ok": True, **c.account}

        if parts == ["settings"] and method == "POST":
            if "show_adult" in data:
                c.cfg["show_adult"] = bool(data["show_adult"])
            if "api_key" in data:
                key = str(data["api_key"]).strip()
                if not key:
                    mgr.set_api_key("")
                    c.account = None
                else:
                    if len(key) > 500 or any(ch.isspace() for ch in key):
                        raise ApiError(400, _("La clave no parece válida."))
                    try:
                        d = nexus.Nexus(key).validate()
                    except nexus.NexusError as e:
                        if "401" in str(e):   # clave rechazada: no se guarda
                            raise ApiError(400, str(e))
                        d = None              # sin conexión u otro fallo: se guarda y se comprueba luego
                    mgr.set_api_key(key)
                    c.account = {"name": d.get("name"), "premium": d.get("premium")} if d else None
            if "language" in data and (data["language"] == "auto" or data["language"] in i18n.available()):
                mgr.config["language"] = data["language"]
                i18n.set_language(data["language"])
            mgr.save_config()
            return {"ok": True, "language": i18n.current(), "nexus_key": bool(mgr.api_key), "account": c.account}


        if len(parts) >= 2 and parts[0] == "game":
            ctx = c.ctx(parts[1])
            sub = parts[2] if len(parts) > 2 else ""
            if sub == "" and method == "GET":
                return ctx.snapshot()
            if sub == "mod" and method == "POST":
                mid, act = data.get("id"), data.get("action")
                if act == "toggle":
                    c.locked_call(ctx.set_enabled, mid, bool(data.get("value")))
                elif act in ("up", "down"):
                    c.locked_call(ctx.move_mod, mid, -1 if act == "up" else 1)
                elif act == "top":
                    c.locked_call(ctx.move_mod, mid, -10**6)
                elif act == "bottom":
                    c.locked_call(ctx.move_mod, mid, 10**6)
                elif act == "remove":
                    c.locked_call(ctx.remove_mod, mid)
                elif act == "rename":
                    name = str(data.get("value", "")).strip()[:200]
                    if name:
                        c.locked_call(ctx.rename_mod, mid, name)
                else:
                    raise ApiError(400, _("Acción desconocida."))
                return ctx.snapshot()
            if sub == "plugin" and method == "POST":
                name, act = data.get("name"), data.get("action")
                if act == "toggle":
                    c.locked_call(ctx.set_plugin_active, name, bool(data.get("value")))
                elif act in ("up", "down"):
                    c.locked_call(ctx.move_plugin, name, -1 if act == "up" else 1)
                else:
                    raise ApiError(400, _("Acción desconocida."))
                return ctx.snapshot()
            if sub == "apply" and method == "POST":
                return c.submit_apply(parts[1]).to_dict()
            if sub == "se" and method == "POST":
                if data.get("action") == "enable":
                    c.locked_call(ctx.se_enable)
                elif data.get("action") == "restore":
                    c.locked_call(ctx.se_restore)
                return ctx.snapshot()
            if sub == "updates" and method == "GET":
                return {"updates": c.check_updates(parts[1])}
            raise ApiError(404, _("No encontrado."))

        if parts[:1] == ["nexus"]:
            if not mgr.api_key:
                raise ApiError(400, _("Primero guarda tu clave de API de Nexus en la consola (pestaña Nexus)."))
            sub = parts[1] if len(parts) > 1 else ""
            if sub == "browse":
                game = q.get("game", "skyrimse")
                ctx = c.ctx(game)
                res = c.browser.browse(GAMES[game]["nexus"], q.get("kind", "trending"), q.get("q", ""),
                                       int(q.get("offset", 0) or 0), 24, c.cfg.get("show_adult", False),
                                       q.get("category") or None, q.get("author") or None)
                inst = c.installed_map(ctx)
                for it in res["items"]:
                    it["installed"] = inst.get(int(it["mod_id"] or 0), [])
                return res
            if sub == "categories":
                game = q.get("game", "skyrimse")
                c.ctx(game)
                return {"categories": c.browser.categories(GAMES[game]["nexus"])}
            if sub == "mod":
                game = q.get("game", "skyrimse")
                ctx = c.ctx(game)
                mod_id = int(q.get("id", 0))
                d = c.browser.mod_detail(GAMES[game]["nexus"], mod_id)
                d = dict(d)
                d["description_html"] = bbcode.to_html(d.pop("description", ""))
                for f in d["files"]:
                    f["description_html"] = bbcode.to_html(f.pop("description", ""), 3000)
                d["installed"] = c.installed_map(ctx).get(mod_id, [])
                d["game"] = game
                return d
            if sub == "install" and method == "POST":
                game = data.get("game")
                job = c.submit_install(game, int(data["mod_id"]), int(data["file_id"]),
                                       data.get("key"), data.get("expires"), data.get("replace_id"))
                return job.to_dict()
            if sub == "link" and method == "POST":
                p = nexus.parse_input(str(data.get("link", "")))
                if not p["mod_id"]:
                    raise ApiError(400, _("No reconozco ese enlace. Copia la dirección de la página del mod en Nexus."))
                game = NEXUS_TO_GAME.get(p["domain"] or "", data.get("game") or "skyrimse")
                if p["domain"] and p["domain"] not in NEXUS_TO_GAME:
                    raise ApiError(400, _("Ese mod es de otro juego ({domain}).", domain=p["domain"]))
                return {"game": game, "mod_id": p["mod_id"], "file_id": p["file_id"],
                        "key": p["key"], "expires": p["expires"]}
            raise ApiError(404, _("No encontrado."))

        if parts[:1] == ["jobs"]:
            if len(parts) == 1 and method == "GET":
                return {"jobs": [j.to_dict() for j in reversed(c.queue.jobs)]}
            if parts[1:] == ["clear"] and method == "POST":
                c.queue.clear_finished()
                return {"ok": True}
            if len(parts) == 3 and method == "POST":
                job = c.queue.get(parts[1])
                if not job:
                    raise ApiError(404, _("Esa tarea ya no existe."))
                if parts[2] == "cancel":
                    c.queue.cancel(job.id)
                elif parts[2] == "choice":
                    if job.state != "needs_choice":
                        raise ApiError(409, _("Esa tarea no está esperando una elección."))
                    if data.get("cancel"):
                        c.queue.cancel(job.id)
                    else:
                        valid = {x["path"] for x in job.choice_req["candidates"]}
                        roots = [r for r in data.get("roots", []) if r in valid]
                        if not roots:
                            raise ApiError(400, _("Marca al menos una carpeta."))
                        kind = "root" if data.get("kind") == "root" else "data"
                        job.answer({"roots": roots, "kind": kind})
                return job.to_dict()
        raise ApiError(404, _("No encontrado."))


def run_headless():
    """Modo servidor sin ventana (servicio en segundo plano)."""
    import signal

    def log(msg):
        print(time.strftime("%H:%M:%S"), msg, flush=True)
    mgr = core.Manager(log=log)
    i18n.set_language(mgr.config.get("language", "auto"))
    comp = Companion(mgr)
    comp.start()
    log(f"PIN: {comp.pin}")
    ev = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: ev.set())
    signal.signal(signal.SIGINT, lambda *_: ev.set())
    ev.wait()
    comp.stop()
    return 0


