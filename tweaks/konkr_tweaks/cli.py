"""Órdenes de terminal: python3 -m konkr_tweaks.cli <orden>

  unwrap-all              quita el lanzador kt-run de las opciones de lanzamiento de todos los juegos
                          (lo usa el desinstalador; Steam tiene que estar cerrado)
  list                    lista los juegos detectados, si tienen lanzador y si hay perfil

Órdenes con salida JSON (las usa el plugin Konkr Toolbox de Decky):
  json-games              juegos instalados con su modo actual
  json-status APPID       estado de un juego
  json-apply APPID MODO [--running]
                          aplica un modo (max, perf, balanced, quality, battery); con --running
                          (juego abierto) los archivos del juego se cambian en su próximo arranque
  json-restore APPID      deja el juego como estaba (archivos originales y sin ajustes propios)
  json-opts APPID         opciones de lanzamiento del juego (catálogo y valores actuales)
  json-set-opt APPID CLAVE VALOR
                          cambia una opción de lanzamiento (se aplica la próxima vez que se abra el juego)
  --lang es|en            idioma de los textos de las órdenes JSON
"""
import json
import os
import sys

from . import i18n, launchopts, profiles, settings, steam, __version__
from .i18n import _


def _out(data, code=0):
    print(json.dumps(data, ensure_ascii=False))
    return code


def _game(appid, root):
    try:
        appid = int(appid)
    except (TypeError, ValueError):
        return None
    return next((g for g in steam.installed_games(root) if g["appid"] == appid), None)


def _status(g, allp, lo):
    gp = profiles.for_game(g, allp)
    st = settings.game_state(g["appid"])
    return {
        "appid": g["appid"], "name": g["name"],
        "profile": bool(gp), "profile_name": (gp.p.get("name") if gp else None),
        "missing": gp.missing_files() if gp else [],
        "mode": st.get("mode") if st.get("custom") else None,
        "pending": bool(st.get("pending")),
        "has_backup": bool(gp and gp.has_backup()),
        "wrapped": settings.wrapper_active(lo.get(g["appid"], "")),
    }


def _opts(appid):
    eff, custom = settings.effective(appid)
    out = []
    for o in launchopts.catalog():
        avail = o.get("avail", True)
        if o.get("only_if_avail") and not avail:
            continue
        out.append({"key": o["key"], "kind": o["kind"], "group": o["group"],
                    "group_label": launchopts.group_label(o["group"]), "label": o["label"],
                    "hint": o["hint"], "avail": avail, "value": eff.get(o["key"]),
                    "choices": [{"value": v, "label": lbl} for v, lbl in o.get("choices", [])]})
    return {"appid": appid, "custom": custom, "options": out}


def json_cmd(cmd, args, root):
    from . import optimize
    if not root:
        return _out({"ok": False, "error": "no-steam"}, 1)
    lo = steam.all_launch_options(root)
    if cmd == "json-games":
        allp = profiles.load_all()
        return _out({"ok": True, "version": __version__, "wrapper": settings.WRAPPER,
                     "games": [_status(g, allp, lo) for g in steam.installed_games(root)]})
    g = _game(args[0] if args else None, root)
    if not g:
        return _out({"ok": False, "error": "no-game"}, 1)
    if cmd == "json-status":
        return _out(dict(_status(g, profiles.load_all(), lo), ok=True))
    if cmd == "json-apply":
        mode = args[1] if len(args) > 1 else ""
        if mode not in optimize.MODES:
            return _out({"ok": False, "error": "bad-mode"}, 1)
        pl = optimize.apply_mode(g, mode, defer_files="--running" in args)
        return _out({"ok": True, "mode": mode, "preset": pl.get("preset"), "resolution": pl.get("resolution"),
                     "fps": pl.get("fps"), "fex": pl["launch"].get("fex"), "profile": pl.get("profile"),
                     "missing": pl.get("missing", []), "deferred": pl.get("deferred", False)})
    if cmd == "json-opts":
        return _out(dict(_opts(g["appid"]), ok=True))
    if cmd == "json-set-opt":
        opt = launchopts.get(args[1]) if len(args) > 2 else None
        if not opt:
            return _out({"ok": False, "error": "bad-option"}, 1)
        try:
            value = launchopts.parse_value(opt, args[2])
        except ValueError:
            return _out({"ok": False, "error": "bad-value"}, 1)
        st = settings.game_state(g["appid"])
        if not st.get("custom"):   # primera opción propia: parte de los ajustes por defecto
            st["custom"] = True
            st["launch"] = {k: v for k, v in settings.defaults().items()}
        st.setdefault("launch", {})[opt["key"]] = value
        settings.save_game_state(g["appid"], st)
        return _out(dict(_opts(g["appid"]), ok=True, key=opt["key"], value=value))
    if cmd == "json-restore":
        gp = profiles.for_game(g)
        restored = gp.restore() if gp else []
        st = settings.game_state(g["appid"])
        for k in ("custom", "launch", "mode", "pending"):
            st.pop(k, None)
        settings.save_game_state(g["appid"], st)
        return _out({"ok": True, "restored": len(restored)})
    return _out({"ok": False, "error": "bad-command"}, 1)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    lang = settings.app_config().get("language", "auto")
    if "--lang" in argv:
        i = argv.index("--lang")
        if i + 1 < len(argv):
            lang = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    i18n.set_language(lang)
    cmd = argv[0] if argv else "list"
    root = steam.steam_root()
    if cmd.startswith("json-"):
        try:
            return json_cmd(cmd, argv[1:], root)
        except Exception as e:  # noqa — el plugin necesita siempre una respuesta JSON
            return _out({"ok": False, "error": f"{type(e).__name__}: {e}"}, 1)
    if not root:
        print(_("No encuentro Steam"))
        return 1
    lo = steam.all_launch_options(root)
    if cmd == "unwrap-all":
        changes = {a: settings.without_wrapper(v) for a, v in lo.items() if settings.wrapper_active(v)}
        if not changes:
            return 0
        if steam.steam_running():
            print(_("Steam sigue abierto."))
            return 2
        steam.set_launch_options(changes, root, os.path.join(settings.DATA_DIR, "backups", "steam"))
        print(_("Hecho: {n} juego(s) actualizados.", n=len(changes)))
        return 0
    if cmd == "list":
        allp = profiles.load_all()
        for g in steam.installed_games(root):
            gp = profiles.for_game(g, allp)
            mark = "kt-run" if settings.wrapper_active(lo.get(g["appid"], "")) else "      "
            print(f"{g['appid']:>9}  {mark}  {'*' if gp else ' '}  {g['name']}")
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
