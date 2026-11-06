"""Lector/escritor del formato VDF de texto de Steam (localconfig.vdf, appmanifest_*.acf…).

Conserva el orden de las claves. Las claves se comparan sin distinguir mayúsculas al buscar.
"""


class VdfError(Exception):
    pass


def _unescape(s):
    out, i = [], 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            n = s[i + 1]
            out.append({"n": "\n", "t": "\t", "\\": "\\", '"': '"'}.get(n, "\\" + n))
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _escape(s):
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t")


def _tokens(text):
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in " \t\r\n":
            i += 1
        elif c == "/" and text.startswith("//", i):
            while i < n and text[i] != "\n":
                i += 1
        elif c in "{}":
            yield c
            i += 1
        elif c == '"':
            j = i + 1
            buf = []
            while j < n:
                if text[j] == "\\" and j + 1 < n:
                    buf.append(text[j:j + 2])
                    j += 2
                    continue
                if text[j] == '"':
                    break
                buf.append(text[j])
                j += 1
            if j >= n:
                raise VdfError("cadena sin cerrar")
            yield ("s", _unescape("".join(buf)))
            i = j + 1
        else:
            j = i
            while j < n and text[j] not in " \t\r\n{}\"":
                j += 1
            yield ("s", text[i:j])
            i = j


def loads(text):
    """Devuelve dict (ordenado) anidado. Valores: str o dict."""
    toks = list(_tokens(text))
    pos = 0

    def parse_obj(top):
        nonlocal pos
        obj = {}
        while pos < len(toks):
            t = toks[pos]
            if t == "}":
                if top:
                    raise VdfError("llave de cierre inesperada")
                pos += 1
                return obj
            if t == "{":
                raise VdfError("llave de apertura inesperada")
            key = t[1]
            pos += 1
            if pos >= len(toks):
                raise VdfError("falta valor")
            v = toks[pos]
            if v == "{":
                pos += 1
                obj[key] = parse_obj(False)
            elif v == "}":
                raise VdfError("falta valor")
            else:
                obj[key] = v[1]
                pos += 1
        if not top:
            raise VdfError("falta llave de cierre")
        return obj
    return parse_obj(True)


def dumps(obj, indent=0):
    tabs = "\t" * indent
    out = []
    for k, v in obj.items():
        if isinstance(v, dict):
            out.append(f'{tabs}"{_escape(k)}"\n{tabs}{{\n{dumps(v, indent + 1)}{tabs}}}\n')
        else:
            out.append(f'{tabs}"{_escape(k)}"\t\t"{_escape(v)}"\n')
    return "".join(out)


def find(obj, *path, create=False):
    """Navega sin distinguir mayúsculas. Con create=True crea los dicts que falten."""
    cur = obj
    for p in path:
        key = next((k for k in cur if k.lower() == str(p).lower()), None)
        if key is None:
            if not create:
                return None
            cur[str(p)] = {}
            key = str(p)
        if not isinstance(cur[key], dict):
            if not create:
                return None
            cur[key] = {}
        cur = cur[key]
    return cur


def get_ci(d, key, default=None):
    if not isinstance(d, dict):
        return default
    k = next((k for k in d if k.lower() == key.lower()), None)
    return d[k] if k is not None else default


def set_ci(d, key, value):
    k = next((k for k in d if k.lower() == key.lower()), key)
    d[k] = value
