"""Cliente mínimo de la API pública v1 de Nexus Mods (solo biblioteca estándar)."""
import http.client
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from . import __version__, APP_NAME
from .i18n import _

API = "https://api.nexusmods.com/v1"


class NexusError(Exception):
    pass


def safe_url(url):
    """Escapa espacios y otros caracteres no válidos (los enlaces de los CDN de Nexus traen el
    nombre del archivo tal cual, p. ej. «Immersive Weapons-16788-2.7z»). Respeta lo ya escapado."""
    u = urllib.parse.urlsplit(url.strip())
    path = urllib.parse.quote(u.path, safe="/%:@!$&'()*+,;=-._~")
    query = urllib.parse.quote(u.query, safe="=&%/:@!$'()*+,;?-._~")
    return urllib.parse.urlunsplit((u.scheme, u.netloc, path, query, u.fragment))


def nice_name(mod_name, f):
    """Nombre para la lista: el del mod, y el del archivo si no es el principal."""
    name = mod_name or f.get("name") or ""
    fname = f.get("name") or ""
    cat = (f.get("category_name") or f.get("category") or "").upper()
    if fname and fname != name and cat != "MAIN":
        name = f"{name} — {fname}"
    return name


def parse_input(text):
    """Acepta un ID, una URL de nexusmods.com o un enlace nxm://.
    Devuelve dict con domain, mod_id, file_id, key, expires (los que haya)."""
    text = (text or "").strip()
    out = {"domain": None, "mod_id": None, "file_id": None, "key": None, "expires": None}
    if not text:
        return out
    if text.isdigit():
        out["mod_id"] = int(text)
        return out
    if text.lower().startswith("nxm://"):
        u = urllib.parse.urlparse(text)
        out["domain"] = u.netloc.lower()
        m = re.match(r"/mods/(\d+)/files/(\d+)", u.path)
        if m:
            out["mod_id"], out["file_id"] = int(m.group(1)), int(m.group(2))
        q = urllib.parse.parse_qs(u.query)
        out["key"] = (q.get("key") or [None])[0]
        out["expires"] = (q.get("expires") or [None])[0]
        return out
    m = re.search(r"nexusmods\.com/([^/]+)/mods/(\d+)", text)
    if m:
        out["domain"], out["mod_id"] = m.group(1).lower(), int(m.group(2))
        fm = re.search(r"[?&]file_id=(\d+)", text)
        if fm:
            out["file_id"] = int(fm.group(1))
    return out


class Nexus:
    def __init__(self, api_key):
        self.api_key = (api_key or "").strip()
        self.rate = {}

    def _headers(self):
        return {
            "apikey": self.api_key,
            "Application-Name": APP_NAME,
            "Application-Version": __version__,
            "User-Agent": f"{APP_NAME}/{__version__} (SteamOS ARM)",
            "Accept": "application/json",
        }

    def _get(self, path, params=None):
        if not self.api_key:
            raise NexusError(_("Falta la clave de API de Nexus (pestaña Nexus)."))
        url = API + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                for h in ("x-rl-daily-remaining", "x-rl-hourly-remaining"):
                    if r.headers.get(h) is not None:
                        self.rate[h] = r.headers.get(h)
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = json.loads(e.read().decode("utf-8")).get("message", "")
            except Exception:
                pass
            if e.code == 401:
                raise NexusError(_("Clave de API no válida (401)."))
            if e.code == 403:
                raise NexusError(_("Nexus ha denegado la descarga (403). Las descargas directas "
                                   "requieren Premium; sin Premium usa el botón 'Mod Manager Download' "
                                   "y pega aquí el enlace nxm://.") + (" " + body if body else ""))
            if e.code == 429:
                raise NexusError(_("Límite de peticiones de Nexus alcanzado (429). Espera un rato."))
            raise NexusError(_("Error HTTP {code} de Nexus.", code=e.code) + (" " + body if body else ""))
        except urllib.error.URLError as e:
            raise NexusError(_("Sin conexión con Nexus: {error}", error=e.reason))
        except (OSError, http.client.HTTPException, ValueError) as e:
            raise NexusError(_("Error de conexión con Nexus: {error}", error=e))

    def validate(self):
        d = self._get("/users/validate.json")
        d["premium"] = bool(d.get("is_premium") or d.get("is_premium?"))
        return d

    def mod_info(self, domain, mod_id):
        return self._get(f"/games/{domain}/mods/{mod_id}.json")

    def files(self, domain, mod_id):
        d = self._get(f"/games/{domain}/mods/{mod_id}/files.json")
        files = d.get("files", [])
        order = {"MAIN": 0, "UPDATE": 1, "OPTIONAL": 2, "MISCELLANEOUS": 3, "OLD_VERSION": 9, "ARCHIVED": 9}
        files.sort(key=lambda f: (order.get((f.get("category_name") or "").upper(), 5),
                                  -(f.get("uploaded_timestamp") or 0)))
        return files

    def download_url(self, domain, mod_id, file_id, key=None, expires=None):
        params = {"key": key, "expires": expires} if key and expires else None
        links = self._get(f"/games/{domain}/mods/{mod_id}/files/{file_id}/download_link.json", params)
        if not links:
            raise NexusError(_("Nexus no ha devuelto enlaces de descarga."))
        return links[0]["URI"]

    def download(self, url, dest_dir, filename=None, progress=None, cancel=None):
        """Descarga a dest_dir. progress(bytes, total). cancel() -> True para abortar."""
        os.makedirs(dest_dir, exist_ok=True)
        if not filename:
            filename = urllib.parse.unquote(os.path.basename(urllib.parse.urlparse(url).path)) or "descarga.bin"
        filename = re.sub(r'[\\/:*?"<>|]', "_", filename)
        dest = os.path.join(dest_dir, filename)
        tmp = dest + ".part"
        req = urllib.request.Request(safe_url(url), headers={"User-Agent": self._headers()["User-Agent"]})
        ok = False
        try:
            self._fetch(req, tmp, progress, cancel)
            os.replace(tmp, dest)
            ok = True
        except urllib.error.HTTPError as e:
            raise NexusError(_("Error HTTP {code} al descargar el archivo.", code=e.code))
        except urllib.error.URLError as e:
            raise NexusError(_("Sin conexión con Nexus: {error}", error=e.reason))
        except (OSError, http.client.HTTPException, ValueError) as e:
            if isinstance(e, OSError) and e.errno == 28:
                raise NexusError(_("No queda espacio en disco para la descarga."))
            raise NexusError(_("Error de conexión con Nexus: {error}", error=e))
        finally:
            if not ok and os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
        return dest

    def _fetch(self, req, tmp, progress, cancel):
        with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            while True:
                if cancel and cancel():
                    raise NexusError(_("Descarga cancelada."))
                chunk = r.read(1024 * 256)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)


# --------------------------------------------------------------------------- explorador (móvil)

GQL = "https://api.nexusmods.com/v2/graphql"
_SEARCH_Q = """
query KmmMods($filter: ModsFilter, $sort: [ModsSort!], $count: Int, $offset: Int) {
  mods(filter: $filter, sort: $sort, count: $count, offset: $offset) {
    totalCount
    nodes { modId name summary version author pictureUrl thumbnailUrl endorsements downloads
            adultContent status updatedAt uploader { name } }
  }
}"""

SORTS = {
    "popular": {"endorsements": {"direction": "DESC"}},
    "downloads": {"downloads": {"direction": "DESC"}},
    "latest_added": {"createdAt": {"direction": "DESC"}},
    "latest_updated": {"updatedAt": {"direction": "DESC"}},
    "relevance": {"relevance": {"direction": "DESC"}},
}


def _norm_v1(m):
    return {
        "mod_id": m.get("mod_id"), "name": m.get("name") or "", "summary": m.get("summary") or "",
        "version": m.get("version") or "", "author": m.get("author") or m.get("uploaded_by") or "",
        "picture": m.get("picture_url"), "endorsements": m.get("endorsement_count") or 0,
        "downloads": m.get("mod_downloads") or 0, "adult": bool(m.get("contains_adult_content")),
        "updated": m.get("updated_timestamp") or 0,
        "available": m.get("available", True) and (m.get("status") in (None, "published")),
    }


def _norm_v2(m):
    import datetime
    upd = 0
    try:
        upd = int(datetime.datetime.fromisoformat(m["updatedAt"].replace("Z", "+00:00")).timestamp())
    except Exception:  # noqa
        pass
    return {
        "mod_id": m.get("modId"), "name": m.get("name") or "", "summary": m.get("summary") or "",
        "version": m.get("version") or "", "author": m.get("author") or (m.get("uploader") or {}).get("name", ""),
        "picture": m.get("thumbnailUrl") or m.get("pictureUrl"), "endorsements": m.get("endorsements") or 0,
        "downloads": m.get("downloads") or 0, "adult": bool(m.get("adultContent")), "updated": upd,
        "available": m.get("status") in (None, "published"),
    }


class Browser(Nexus):
    """Consultas para el explorador del móvil, con caché de 5 minutos para ahorrar peticiones."""
    TTL = 300

    def __init__(self, api_key):
        super().__init__(api_key)
        self._cache = {}

    def _cached(self, key, fn):
        hit = self._cache.get(key)
        if hit and time.time() - hit[0] < self.TTL:
            return hit[1]
        val = fn()
        self._cache[key] = (time.time(), val)
        if len(self._cache) > 300:
            for k in sorted(self._cache, key=lambda k: self._cache[k][0])[:100]:
                self._cache.pop(k, None)
        return val

    def _graphql(self, query, variables):
        body = json.dumps({"query": query, "variables": variables}).encode("utf-8")
        h = self._headers()
        h["Content-Type"] = "application/json"
        if not self.api_key:
            h.pop("apikey")
        req = urllib.request.Request(GQL, data=body, headers=h, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                d = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise NexusError(_("Error HTTP {code} en la búsqueda de Nexus.", code=e.code))
        except (OSError, http.client.HTTPException, ValueError) as e:
            raise NexusError(_("Sin conexión con Nexus: {error}", error=e))
        if d.get("errors"):
            raise NexusError("Nexus: " + "; ".join(x.get("message", "?") for x in d["errors"])[:300])
        return d.get("data") or {}

    def categories(self, domain):
        """Categorías de mods del juego: [{id, name, parent}] (nombres tal cual los da Nexus)."""
        def fetch():
            d = self._get(f"/games/{domain}.json")
            out = []
            for c in d.get("categories", []):
                if c.get("category_id") is None or not c.get("name"):
                    continue
                parent = c.get("parent_category")
                out.append({"id": c["category_id"], "name": c["name"],
                            "parent": parent if isinstance(parent, int) and parent else None})
            return out
        key = ("cats", domain)
        hit = self._cache.get(key)
        if hit and time.time() - hit[0] < 86400:
            return hit[1]
        val = fetch()
        self._cache[key] = (time.time(), val)
        return val

    def browse(self, domain, kind="trending", query="", offset=0, count=20, show_adult=False, category=None,
               author=None):
        """kind: trending | popular | downloads | latest_added | latest_updated | relevance.
        query: busca por nombre. category: nombre de categoría de Nexus. author: autor o uploader."""
        query = (query or "").strip()
        if kind == "trending" and not query and not category and not author:
            raw = self._cached(("v1", domain, "trending"),
                               lambda: self._get(f"/games/{domain}/mods/trending.json"))
            items, total = [_norm_v1(m) for m in raw], len(raw)
        else:
            flt = {"gameDomainName": [{"value": domain, "op": "EQUALS"}]}
            if not show_adult:
                flt["adultContent"] = [{"value": False, "op": "EQUALS"}]
            if query:
                flt["nameStemmed"] = [{"value": query, "op": "WILDCARD"}]
            if category:
                flt["categoryName"] = [{"value": category, "op": "EQUALS"}]
            if author:
                flt["filter"] = [{"op": "OR", "author": [{"value": author, "op": "WILDCARD"}],
                                  "uploader": [{"value": author, "op": "WILDCARD"}]}]
            if kind == "trending":
                kind = "popular"
            sort = SORTS.get(kind if kind in SORTS else ("relevance" if query else "popular"))
            variables = {"filter": flt, "sort": [sort], "count": count, "offset": offset}
            key = ("v2", json.dumps(variables, sort_keys=True))
            data = self._cached(key, lambda: self._graphql(_SEARCH_Q, variables))
            page = data.get("mods") or {}
            items, total = [_norm_v2(m) for m in page.get("nodes", [])], page.get("totalCount", 0)
        items = [i for i in items if i["available"] and (show_adult or not i["adult"])]
        return {"items": items, "total": total, "offset": offset}

    def mod_detail(self, domain, mod_id):
        info = self._cached(("info", domain, mod_id), lambda: self.mod_info(domain, mod_id))
        files = self._cached(("files", domain, mod_id), lambda: self.files(domain, mod_id))
        out = _norm_v1(info)
        out["description"] = info.get("description") or ""
        out["category_id"] = info.get("category_id")
        out["url"] = f"https://www.nexusmods.com/{domain}/mods/{mod_id}"
        out["files"] = [{
            "file_id": f["file_id"], "name": f.get("name") or f.get("file_name"), "version": f.get("version") or "",
            "category": (f.get("category_name") or "").upper(), "size_kb": f.get("size_kb") or 0,
            "file_name": f.get("file_name") or "", "uploaded": f.get("uploaded_timestamp") or 0,
            "description": f.get("description") or "", "primary": bool(f.get("is_primary")),
        } for f in files if (f.get("category_name") or "").upper() not in ("ARCHIVED", "DELETED", "REMOVED")]
        return out

    def updated_since(self, domain, period="1m"):
        """{mod_id: último timestamp de actualización} de los mods actualizados en el periodo (1d, 1w, 1m)."""
        raw = self._cached(("upd", domain, period),
                           lambda: self._get(f"/games/{domain}/mods/updated.json", {"period": period}))
        return {m["mod_id"]: m.get("latest_file_update") or 0
                for m in raw}
