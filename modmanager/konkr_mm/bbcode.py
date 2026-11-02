"""Conversión segura de las descripciones BBCode de Nexus a HTML para el móvil.
Primero se escapa TODO el HTML y después solo se convierten etiquetas BBCode conocidas,
con URLs limitadas a http(s). Lo que no se reconoce se elimina."""
import html
import re

_URL_OK = re.compile(r"^https?://[^\s\"'<>]+$", re.I)


def _safe_url(u):
    u = html.unescape(u.strip())
    return html.escape(u, quote=True) if _URL_OK.match(u) else None


def _img(m):
    url = _safe_url(m.group(1))
    return f'<img src="{url}" loading="lazy" alt="">' if url else ""


def _youtube(m):
    vid = m.group(1).strip()
    if re.fullmatch(r"[\w-]{6,20}", vid):
        return (f'<a href="https://www.youtube.com/watch?v={vid}" target="_blank" '
                f'rel="noopener noreferrer">▶ Vídeo de YouTube</a>')
    return ""


def _list(m):
    body = m.group(2)
    items = [i.strip() for i in re.split(r"\[\*\]", body) if i.strip()]
    tag = "ol" if m.group(1) else "ul"
    return f"<{tag}>" + "".join(f"<li>{i}</li>" for i in items) + f"</{tag}>"


SIMPLE = [
    (r"\[b\](.*?)\[/b\]", r"<b>\1</b>"),
    (r"\[i\](.*?)\[/i\]", r"<i>\1</i>"),
    (r"\[u\](.*?)\[/u\]", r"<u>\1</u>"),
    (r"\[s\](.*?)\[/s\]", r"<s>\1</s>"),
    (r"\[center\](.*?)\[/center\]", r'<div class="c">\1</div>'),
    (r"\[right\](.*?)\[/right\]", r"<div>\1</div>"),
    (r"\[left\](.*?)\[/left\]", r"<div>\1</div>"),
    (r"\[quote(?:=[^\]]*)?\](.*?)\[/quote\]", r"<blockquote>\1</blockquote>"),
    (r"\[code\](.*?)\[/code\]", r"<pre>\1</pre>"),
    (r"\[spoiler\](.*?)\[/spoiler\]", r"<details><summary>Spoiler</summary>\1</details>"),
    (r"\[heading\](.*?)\[/heading\]", r"<h4>\1</h4>"),
    (r"\[size=(?:5|6|7|[2-9]\d)[^\]]*\](.*?)\[/size\]", r"<h4>\1</h4>"),
]


def to_html(text, max_len=60000):
    if not text:
        return ""
    t = html.escape(text[:max_len], quote=True)
    t = t.replace("&lt;br /&gt;", "\n").replace("&lt;br/&gt;", "\n").replace("&lt;br&gt;", "\n")
    t = t.replace("\r\n", "\n")
    for _ in range(3):  # etiquetas anidadas
        for pat, rep in SIMPLE:
            t = re.sub(pat, rep, t, flags=re.I | re.S)
        t = re.sub(r"\[list(=1)?\](.*?)\[/list\]", _list, t, flags=re.I | re.S)
    t = re.sub(r"\[url=([^\]]+)\](.*?)\[/url\]", lambda m: _link_pair(m.group(1), m.group(2)), t, flags=re.I | re.S)
    t = re.sub(r"\[url\](.*?)\[/url\]", lambda m: _link_pair(m.group(1), m.group(1)), t, flags=re.I | re.S)
    t = re.sub(r"\[img(?:[^\]]*)\](.*?)\[/img\]", _img, t, flags=re.I | re.S)
    t = re.sub(r"\[youtube\](.*?)\[/youtube\]", _youtube, t, flags=re.I | re.S)
    t = re.sub(r"\[line\]", "<hr>", t, flags=re.I)
    t = re.sub(r"\[/?[a-z*]+(?:=[^\]]*)?\]", "", t, flags=re.I)  # resto de etiquetas fuera
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip().replace("\n", "<br>")


def _link_pair(url, text):
    u = _safe_url(url)
    if not u:
        return text
    return f'<a href="{u}" target="_blank" rel="noopener noreferrer">{text}</a>'
