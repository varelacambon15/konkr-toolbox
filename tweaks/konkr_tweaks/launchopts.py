"""Catálogo de opciones de lanzamiento que se pueden activar por juego.

Lo usan la interfaz (gui.py), las órdenes JSON del plugin Konkr Toolbox (cli.py) y, para saber qué
claves existen, settings.py. Cómo se convierte cada opción en variables, argumentos o núcleos de CPU
está en settings.build_launch() y settings.cpu_affinity().

Cada entrada: key, kind ("bool" | "choice"), group, label, hint, choices [(valor, texto)], avail,
int (el valor se guarda como número).
"""
import os
import shutil

from .i18n import _

GROUPS = ["perf", "stab", "extra"]


def group_label(g):
    return {"perf": _("Rendimiento"), "stab": _("Estabilidad"), "extra": _("Extras y diagnóstico")}[g]


def fps_choices():
    return [(0, _("Sin límite"))] + [(v, f"{v} fps") for v in (30, 40, 45, 60)]


def catalog():
    from . import settings
    fex = settings.fex_available()
    return [
        # ---------------------------------------------------------------- rendimiento
        {"key": "fex", "kind": "choice", "group": "perf", "avail": fex, "only_if_avail": True,
         "label": _("Traductor FEX"),
         "hint": _("fast: más fps y seguro. fastest: aún más, puede fallar. compat: si el juego se cierra."),
         "choices": [("none", _("Sin cambios")), ("fast", "fast"), ("fastest", "fastest"), ("compat", "compat")]},
        {"key": "fps", "kind": "choice", "group": "perf", "int": True,
         "label": _("Límite de fps (DirectX)"),
         "hint": _("Ahorra batería y estabiliza. El de Steam (menú rápido) sirve para todos."),
         "choices": fps_choices()},
        {"key": "vsync_off", "kind": "bool", "group": "perf",
         "label": _("Quitar el vsync del juego"),
         "hint": _("Evita que los fps caigan de golpe de 60 a 30 cuando el juego no llega a 60. DirectX 9-11 (DXVK).")},
        {"key": "bigcores", "kind": "bool", "group": "perf", "avail": bool(fast_cores()),
         "label": _("Solo núcleos rápidos"),
         "hint": _("El juego no usa los núcleos de bajo consumo. Puede quitar tirones en juegos que tiran mucho de CPU.")},
        {"key": "shader_cache", "kind": "bool", "group": "perf",
         "label": _("Caché de shaders grande"),
         "hint": _("Guarda más shaders ya compilados (hasta 4 GB): menos tirones al volver a zonas ya vistas.")},
        {"key": "latency", "kind": "bool", "group": "perf",
         "label": _("Menos retraso de los controles"),
         "hint": _("Responde antes a los botones. Puede bajar algo los fps. DirectX 9-11 (DXVK).")},
        {"key": "gfx_api", "kind": "choice", "group": "perf",
         "label": _("Forzar API gráfica"),
         "hint": _("-dx11 / -dx12: muchos juegos de Unreal. -force-vulkan / -force-d3d11: juegos de Unity. "
                   "Si el juego no arranca, vuelve a «Sin cambios»."),
         "choices": [("", _("Sin cambios")), ("-dx11", "-dx11"), ("-dx12", "-dx12"),
                     ("-force-vulkan", "-force-vulkan"), ("-force-d3d11", "-force-d3d11")]},
        # ---------------------------------------------------------------- estabilidad
        {"key": "ntsync", "kind": "bool", "group": "stab",
         "label": _("NTSync"), "hint": _("Sincronización más rápida en Proton recientes.")},
        {"key": "sync_compat", "kind": "bool", "group": "stab",
         "label": _("Sincronización compatible"),
         "hint": _("Desactiva esync, fsync y NTSync. Para juegos que se congelan o no pasan de la pantalla de carga.")},
        {"key": "heap_delay_free", "kind": "bool", "group": "stab",
         "label": _("Arreglo de cierres aleatorios"),
         "hint": _("Retrasa la liberación de memoria. Corrige juegos que se cierran solos de vez en cuando.")},
        {"key": "wined3d", "kind": "bool", "group": "stab",
         "label": _("Usar WineD3D en vez de DXVK"),
         "hint": _("Para juegos DirectX 9-11 con pantalla negra o gráficos rotos. Suele ir más lento.")},
        {"key": "mod_dlls", "kind": "bool", "group": "stab",
         "label": _("Cargar DLL de mods"),
         "hint": _("Usa las dinput8.dll, winmm.dll y version.dll de la carpeta del juego (cargadores de mods, ASI, etc.).")},
        # ---------------------------------------------------------------- extras
        {"key": "deck", "kind": "bool", "group": "extra",
         "label": _("Modo Steam Deck"), "hint": _("Algunos juegos eligen ajustes y controles de Deck.")},
        {"key": "mangohud", "kind": "bool", "group": "extra", "avail": bool(shutil.which("mangohud")),
         "label": "MangoHud", "hint": _("Superposición con fps, temperaturas y uso.")},
        {"key": "dxvk_hud", "kind": "bool", "group": "extra", "label": _("Contador de fps (DXVK)"), "hint": ""},
        {"key": "quiet_logs", "kind": "bool", "group": "extra",
         "label": _("Sin registros de DXVK/VKD3D"),
         "hint": _("No escribe registros mientras juegas. Ahorra algo de trabajo al disco.")},
        {"key": "proton_log", "kind": "bool", "group": "extra",
         "label": _("Registro de Proton"), "hint": _("Guarda ~/steam-<appid>.log para investigar fallos.")},
    ]


def get(key):
    return next((o for o in catalog() if o["key"] == key), None)


def parse_value(opt, raw):
    """Convierte un valor recibido como texto (orden JSON) al tipo de la opción. ValueError si no vale."""
    if opt["kind"] == "bool":
        if isinstance(raw, bool):
            return raw
        s = str(raw).strip().lower()
        if s in ("1", "true", "yes", "on", "si", "sí"):
            return True
        if s in ("0", "false", "no", "off", ""):
            return False
        raise ValueError(raw)
    vals = [c[0] for c in opt["choices"]]
    v = int(raw) if opt.get("int") else str(raw)
    if v not in vals:
        raise ValueError(raw)
    return v


# --------------------------------------------------------------------------- núcleos de CPU

def _max_freqs():
    out = {}
    base = "/sys/devices/system/cpu"
    try:
        names = os.listdir(base)
    except OSError:
        return out
    for n in names:
        if n.startswith("cpu") and n[3:].isdigit():
            try:
                with open(os.path.join(base, n, "cpufreq", "cpuinfo_max_freq")) as f:
                    out[int(n[3:])] = int(f.read().strip())
            except (OSError, ValueError):
                pass
    return out


def fast_cores():
    """Núcleos sin el grupo más lento (los de bajo consumo). Vacío si todos son iguales o no se sabe.
    Snapdragon 8 Gen 3: deja fuera los 2 Cortex-A520 y quedan 6 núcleos."""
    freqs = _max_freqs()
    if len(set(freqs.values())) < 2:
        return set()
    slow = min(freqs.values())
    fast = {c for c, f in freqs.items() if f > slow}
    try:
        fast &= os.sched_getaffinity(0)
    except (AttributeError, OSError):
        pass
    return fast if len(fast) >= 2 else set()
