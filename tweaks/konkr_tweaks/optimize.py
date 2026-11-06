"""Modos de juego (Máximo rendimiento, Rendimiento, Equilibrado, Calidad, Batería) y
«Optimizar para este equipo». Un modo combina: preset gráfico del perfil, resolución interna,
preset del traductor FEX, límite de fps y ajustes de arranque."""
from . import device, profiles, settings

MODES = ["max", "perf", "balanced", "quality", "battery"]

PLAN = {
    #           gráficos     resolución   FEX        fps  deck*
    "max":      ("lowest",   "smallest",  "fastest", 0,   True),
    "perf":     ("lowest",   "1280x720",  "fast",    0,   True),
    "balanced": ("balanced", "1280x720",  "fast",    0,   False),
    "quality":  ("quality",  "1920x1080", "fast",    0,   False),
    "battery":  ("lowest",   "1280x720",  "fast",    30,  True),
}
# *el modo Steam Deck solo se usa en juegos sin perfil propio (algunos eligen así ajustes ligeros)


def _fallback(preset, available):
    order = {"lowest": ["lowest", "balanced", "quality"], "balanced": ["balanced", "lowest", "quality"],
             "quality": ["quality", "balanced", "lowest"]}[preset]
    return next((p for p in order if p in available), None)


def plan(mode, gp, dev=None):
    """Lo que haría un modo en este juego (sin aplicar nada)."""
    dev = dev or device.info()
    gfx, res, fex, fps, deck = PLAN[mode]
    launch = dict(settings.DEFAULTS)
    if gp and gp.p.get("launch"):
        launch.update(gp.p["launch"])
    launch.update({"fex": fex, "fps": fps, "ntsync": True, "deck": bool(deck and not gp)})
    if not (dev["arm"] or settings.fex_available()):
        launch["fex"] = "none"   # en un PC x86 no hay traductor
    out = {"mode": mode, "launch": launch, "preset": None, "resolution": None, "fps": fps}
    if gp:
        out["preset"] = _fallback(gfx, gp.presets)
        choices = (gp.p.get("resolution") or {}).get("choices", [])
        if choices:
            out["resolution"] = choices[0] if res == "smallest" else (res if res in choices else None)
    return out


def apply_mode(game, mode, all_profiles=None, dev=None, resolution=None, lock=None, defer_files=False):
    """Aplica un modo a un juego. resolution: forzar otra resolución ('' = no cambiar).
    defer_files: con el juego abierto no se tocan sus archivos (el juego los sobrescribiría al
    cerrarse); se apuntan como pendientes y kt-run los aplica en el siguiente arranque."""
    dev = dev or device.info()
    gp = profiles.for_game(game, all_profiles)
    pl = plan(mode, gp, dev)
    if resolution is not None:
        pl["resolution"] = resolution or None
    st = settings.game_state(game["appid"])
    keep = st.get("launch", {})
    for k in settings.PERSONAL:   # lo personal (argumentos, opciones de lanzamiento…) se conserva
        if k in keep:
            pl["launch"][k] = keep[k]
    st.update({"custom": True, "launch": pl["launch"], "mode": mode})
    st.pop("pending", None)
    if gp:
        st["profile_args"] = gp.p.get("args", "")
        if defer_files:
            st["pending"] = {"mode": mode, "resolution": resolution, "lock": lock}
    settings.save_game_state(game["appid"], st)
    pl.update({"missing": [], "profile": bool(gp), "args": gp.p.get("args", "") if gp else "",
               "deferred": bool(gp and defer_files)})
    if gp and defer_files:
        pl["missing"] = gp.missing_files()
    elif gp:
        pl["missing"] = gp.missing_files()
        if not pl["missing"]:
            gp.apply(pl["preset"], pl["resolution"], lock=gp.lockable() if lock is None else lock, fps=pl["fps"])
            st = settings.game_state(game["appid"])
            st["mode"] = mode
            settings.save_game_state(game["appid"], st)
        else:
            pl["preset"] = pl["resolution"] = None
    return pl


def apply_pending(appid):
    """Lo llama kt-run antes de arrancar: aplica un modo que se eligió con el juego abierto."""
    st = settings.game_state(appid)
    pend = st.get("pending")
    if not pend:
        return False
    from . import steam
    game = next((g for g in steam.installed_games() if g["appid"] == int(appid)), None)
    if game:
        apply_mode(game, pend.get("mode", st.get("mode", "balanced")),
                   resolution=pend.get("resolution"), lock=pend.get("lock"))
    else:
        st.pop("pending", None)
        settings.save_game_state(appid, st)
    return True


def recommended_mode(dev=None):
    dev = dev or device.info()
    return {"low": "perf", "mid": "balanced", "high": "quality"}[dev["tier"]]


def auto_optimize(game, all_profiles=None, dev=None):
    dev = dev or device.info()
    return apply_mode(game, recommended_mode(dev), all_profiles, dev)


def recommended_defaults(dev=None):
    dev = dev or device.info()
    rec = dict(settings.DEFAULTS)
    rec.update({"ntsync": True, "deck": dev["tier"] == "low"})
    if dev["arm"] or settings.fex_available():
        rec["fex"] = "fast"
    return rec
