"""Qué equipo es: arquitectura, memoria, CPU y si es un portátil de mano conocido.
Con eso se decide qué perfil recomendar al pulsar «Optimizar para este equipo»."""
import os
import platform


def _read(path):
    try:
        with open(path, "rb") as f:
            return f.read().decode("utf-8", "replace").strip("\x00\n ")
    except OSError:
        return ""


def ram_gb():
    try:
        for line in open("/proc/meminfo"):
            if line.startswith("MemTotal:"):
                return round(int(line.split()[1]) / 1048576, 1)
    except OSError:
        pass
    return 0.0


def model():
    for p in ("/sys/firmware/devicetree/base/model", "/proc/device-tree/model",
              "/sys/class/dmi/id/product_name"):
        v = _read(p)
        if v:
            return v
    return ""


def cpu_name():
    try:
        for line in open("/proc/cpuinfo"):
            low = line.lower()
            if low.startswith(("model name", "hardware")):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or platform.machine()


def info():
    arch = platform.machine().lower()
    mem = ram_gb()
    mdl = model()
    cores = os.cpu_count() or 0
    is_arm = arch in ("aarch64", "arm64")
    # Nivel: "low" para equipos que traducen x86 (ARM + FEX) o con poca memoria compartida.
    tier = "low" if (is_arm or mem and mem <= 10) else ("mid" if mem <= 20 else "high")
    return {"arch": arch, "arm": is_arm, "ram_gb": mem, "model": mdl, "cpu": cpu_name(), "cores": cores,
            "tier": tier, "konkr": "konkr" in mdl.lower() or "pocket fit" in mdl.lower()}
