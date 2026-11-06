#!/usr/bin/env python3
"""Comprueba las traducciones / checks translations.

  python3 tools/i18n_check.py            -> lista textos sin traducir en cada idioma
  python3 tools/i18n_check.py --update   -> añade las claves que falten (vacías) y quita las que ya no se usan

Recoge los textos de _("...") en el código Python.
"""
import ast
import json
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "konkr_tweaks")
LOCALE = os.path.join(ROOT, "locale")


def python_strings():
    out = []
    for f in sorted(os.listdir(ROOT)):
        if not f.endswith(".py") or f == "qrcodegen.py":
            continue
        tree = ast.parse(open(os.path.join(ROOT, f), encoding="utf-8").read())
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_"
                    and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                out.append(node.args[0].value)
    return out


def main():
    keys = []
    for s in python_strings():
        if s not in keys:
            keys.append(s)
    update = "--update" in sys.argv
    bad = 0
    for f in sorted(os.listdir(LOCALE)):
        if not f.endswith(".json"):
            continue
        path = os.path.join(LOCALE, f)
        cat = json.load(open(path, encoding="utf-8"))
        missing = [k for k in keys if not cat.get(k)]
        unused = [k for k in cat if not k.startswith("__") and k not in keys]
        ph_bad = [k for k in keys if cat.get(k) and set(re.findall(r"\{\w+\}", k)) != set(re.findall(r"\{\w+\}", cat[k]))]
        print(f"{f}: {len(keys) - len(missing)}/{len(keys)} traducidos, {len(unused)} sin uso, "
              f"{len(ph_bad)} con {{marcadores}} distintos")
        for k in missing:
            print("   FALTA:", k)
        for k in ph_bad:
            print("   MARCADORES:", k)
        bad += len(missing) + len(ph_bad)
        if update:
            new = {k: v for k, v in cat.items() if k.startswith("__")}
            for k in keys:
                new[k] = cat.get(k, "")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(new, fh, ensure_ascii=False, indent=1)
                fh.write("\n")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
