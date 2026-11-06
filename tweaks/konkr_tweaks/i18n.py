"""Traducciones / translations.

Los textos del programa están escritos en español y sirven de clave. Cada idioma es un
archivo locale/<código>.json con pares {"texto en español": "traducción"}.
Para añadir un idioma: copia locale/en.json a locale/<código>.json y traduce los valores
(no toques las claves ni lo que va entre llaves, como {name}).

Program texts are written in Spanish and used as keys. Each language is a file
locale/<code>.json with {"Spanish text": "translation"} pairs. To add a language, copy
locale/en.json to locale/<code>.json and translate the values (keep keys and {placeholders}).
"""
import json
import os

LOCALE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "locale")
SOURCE_LANG = "es"

_lang = SOURCE_LANG
_catalog = {}


def available():
    """{código: nombre del idioma en su propio idioma}"""
    langs = {SOURCE_LANG: "Español"}
    try:
        for f in sorted(os.listdir(LOCALE_DIR)):
            if f.endswith(".json"):
                code = f[:-5]
                try:
                    with open(os.path.join(LOCALE_DIR, f), encoding="utf-8") as fh:
                        langs[code] = json.load(fh).get("__language_name__", code)
                except (OSError, ValueError):
                    pass
    except OSError:
        pass
    return langs


def system_language():
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        val = os.environ.get(var, "")
        if val and val not in ("C", "POSIX") and not val.startswith("C."):
            return val.split(":")[0].split(".")[0].split("_")[0].lower()
    return "en"


def resolve(pref):
    """'auto' o un código -> código de idioma disponible (si no hay, inglés)."""
    langs = available()
    code = (pref or "auto").lower()
    if code == "auto":
        code = system_language()
    if code in langs:
        return code
    return "en" if "en" in langs else SOURCE_LANG


def set_language(pref):
    global _lang, _catalog
    code = resolve(pref)
    cat = {}
    if code != SOURCE_LANG:
        try:
            with open(os.path.join(LOCALE_DIR, code + ".json"), encoding="utf-8") as fh:
                cat = {k: v for k, v in json.load(fh).items() if not k.startswith("__") and v}
        except (OSError, ValueError):
            cat = {}
    _lang, _catalog = code, cat
    return code


def current():
    return _lang


def catalog():
    return dict(_catalog)


def _(text, **kw):
    t = _catalog.get(text, text)
    if kw:
        try:
            return t.format(**kw)
        except (KeyError, IndexError, ValueError):
            return text.format(**kw)
    return t
