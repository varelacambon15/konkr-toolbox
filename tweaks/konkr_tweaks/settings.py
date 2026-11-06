"""Ajustes por juego y cómo se convierten en variables de entorno al lanzar el juego.
Lo usan la interfaz y el lanzador kt-run (que no carga GTK)."""
import json
import os
import shlex
import shutil
import tempfile

CONFIG_DIR = os.path.expanduser("~/.config/konkr-tweaks")
DATA_DIR = os.path.expanduser("~/.local/share/konkr-tweaks")
STATE_DIR = os.path.expanduser("~/.local/state/konkr-tweaks")
WRAPPER = "~/.local/bin/kt-run"

DEFAULTS = {
    "fex": "none",        # none | fast | fastest | compat
    "ntsync": False,
    "fps": 0,             # 0 = sin límite
    "deck": False,        # SteamDeck=1
    "mangohud": False,
    "proton_log": False,
    "dxvk_hud": False,
    "args": "",
    "env": "",
    # opciones de lanzamiento (catálogo en launchopts.py)
    "vsync_off": False,
    "bigcores": False,
    "shader_cache": False,
    "latency": False,
    "gfx_api": "",
    "sync_compat": False,
    "heap_delay_free": False,
    "wined3d": False,
    "mod_dlls": False,
    "quiet_logs": False,
}
# Ajustes que son del usuario: un modo (Rendimiento, Calidad…) no los cambia
PERSONAL = ("args", "env", "mangohud", "dxvk_hud", "proton_log", "vsync_off", "bigcores", "shader_cache",
            "latency", "gfx_api", "sync_compat", "heap_delay_free", "wined3d", "mod_dlls", "quiet_logs")

FEX_PRESETS = {
    # mismos valores que el script konkr-game del port de SteamOS ARM
    "fast": {"FEX_X87REDUCEDPRECISION": "1"},
    "fastest": {"FEX_X87REDUCEDPRECISION": "1", "FEX_TSOENABLED": "0"},
    "compat": {"FEX_TSOENABLED": "1", "FEX_VECTORTSOENABLED": "1", "FEX_STRICTINPROCESSSPLITLOCKS": "1",
               "FEX_X87REDUCEDPRECISION": "0"},
}


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".tmp-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def app_config():
    return _load(os.path.join(CONFIG_DIR, "config.json"), {})


def save_app_config(cfg):
    _save(os.path.join(CONFIG_DIR, "config.json"), cfg)


def defaults():
    d = dict(DEFAULTS)
    d.update(_load(os.path.join(CONFIG_DIR, "defaults.json"), {}))
    return d


def save_defaults(values):
    _save(os.path.join(CONFIG_DIR, "defaults.json"), {k: values[k] for k in DEFAULTS if k in values})


def game_path(appid):
    return os.path.join(CONFIG_DIR, "games", f"{appid}.json")


def game_state(appid):
    """Datos guardados del juego (ajustes propios, perfil aplicado…)."""
    return _load(game_path(appid), {})


def save_game_state(appid, state):
    _save(game_path(appid), state)


def effective(appid):
    """Ajustes que se aplican al lanzar: los propios del juego o, si no tiene, los de por defecto."""
    st = game_state(appid)
    eff = defaults()
    if st.get("custom"):
        eff.update({k: v for k, v in st.get("launch", {}).items() if k in DEFAULTS})
    return eff, bool(st.get("custom"))


def launch_settings(appid):
    """Lo que usa kt-run: ajustes efectivos + argumentos que añade el perfil gráfico (resolución, etc.)."""
    eff, _custom = effective(appid)
    st = game_state(appid)
    extra = " ".join(x for x in (st.get("profile_args", ""), st.get("resolution_args", "")) if x)
    if extra:
        eff = dict(eff, args=(eff.get("args", "") + " " + extra).strip())
    return eff


def fex_available():
    return any(shutil.which(x) for x in ("FEXInterpreter", "FEXBash", "FEXLoader", "konkr-game")) or \
        os.path.exists("/usr/bin/konkr-game")


def build_launch(s):
    """-> (env, prefix, extra_args) a partir de un dict de ajustes."""
    env, prefix, args = {}, [], []
    env.update(FEX_PRESETS.get(s.get("fex"), {}))
    if s.get("sync_compat"):
        env["PROTON_NO_ESYNC"] = "1"
        env["PROTON_NO_FSYNC"] = "1"
        env["PROTON_USE_NTSYNC"] = "0"
    elif s.get("ntsync"):
        env["PROTON_USE_NTSYNC"] = "1"
    try:
        fps = int(s.get("fps") or 0)
    except ValueError:
        fps = 0
    if fps > 0:
        env["DXVK_FRAME_RATE"] = str(fps)   # DirectX 9-11
        env["VKD3D_FRAME_RATE"] = str(fps)  # DirectX 12
    if s.get("deck"):
        env["SteamDeck"] = "1"
    if s.get("mangohud"):
        env["MANGOHUD"] = "1"
    if s.get("proton_log"):
        env["PROTON_LOG"] = "1"
    if s.get("dxvk_hud"):
        env["DXVK_HUD"] = "fps"
    dxvk = []
    if s.get("vsync_off"):
        dxvk += ["dxgi.syncInterval = 0", "d3d9.presentInterval = 0"]
    if s.get("latency"):
        dxvk += ["dxgi.maxFrameLatency = 1", "d3d9.maxFrameLatency = 1"]
    if dxvk:
        env["DXVK_CONFIG"] = "; ".join(dxvk)
    if s.get("shader_cache"):
        env["MESA_SHADER_CACHE_MAX_SIZE"] = "4G"
    if s.get("heap_delay_free"):
        env["PROTON_HEAP_DELAY_FREE"] = "1"
    if s.get("wined3d"):
        env["PROTON_USE_WINED3D"] = "1"
    if s.get("mod_dlls"):
        env["WINEDLLOVERRIDES"] = "dinput8,winmm,version=n,b"
    if s.get("quiet_logs") and not s.get("proton_log"):
        env.update({"DXVK_LOG_LEVEL": "none", "VKD3D_DEBUG": "none", "VKD3D_SHADER_DEBUG": "none"})
    for tok in _split(s.get("env", "")):
        if "=" in tok and not tok.startswith("="):
            k, v = tok.split("=", 1)
            if k.replace("_", "").isalnum():
                env[k] = v
    args = _split(s.get("args", ""))
    api = s.get("gfx_api") or ""
    if api.startswith("-") and api not in args:
        args.append(api)
    return env, prefix, args


def cpu_affinity(s):
    """Núcleos a los que se limita el juego (opción «Solo núcleos rápidos»), o None."""
    if not s.get("bigcores"):
        return None
    from .launchopts import fast_cores
    return fast_cores() or None


def _split(text):
    try:
        return shlex.split(text or "")
    except ValueError:
        return (text or "").split()


# --------------------------------------------------------------------------- opciones de lanzamiento

def wrapper_active(launch_options):
    return "kt-run" in (launch_options or "")


def with_wrapper(launch_options):
    """Devuelve (nuevas_opciones, preset_fex_importado). Si había 'konkr-game X %command%',
    se quita y su preset pasa a los ajustes del programa (si no, mandaría konkr-game)."""
    import re
    lo = (launch_options or "").strip()
    if wrapper_active(lo):
        return lo, None
    fex = None
    m = re.search(r"(?:\S*/)?konkr-game\s+(fast|fastest|compat)\s+", lo)
    if m:
        fex = m.group(1)
        lo = (lo[:m.start()] + lo[m.end():]).strip()
    if "%command%" in lo:
        new = lo.replace("%command%", f"{WRAPPER} %command%", 1)
    elif lo:
        new = f"{WRAPPER} %command% {lo}"
    else:
        new = f"{WRAPPER} %command%"
    return new, fex


def without_wrapper(launch_options):
    lo = (launch_options or "").replace(f"{WRAPPER} ", "").replace(WRAPPER, "")
    lo = " ".join(lo.split())
    return "" if lo == "%command%" else lo
