"""Editores para los distintos formatos de configuración de los juegos.
Todos conservan lo que no tocan y guardan con escritura atómica.

Tipos:
  ini   [Sección] clave=valor                      (Bethesda, Unreal)
  xml   <graphics><Elemento value="x"/></graphics>  (GTA V settings.xml)
  call  Comando(args)                               (Dying Light video.scr)
  kv    Clave = "valor"  // comentario             (Black Ops III config.ini, BeamNG)
  cfg   comando valor                               (Source: autoexec.cfg)
  reg   registro de Wine (user.reg), solo valores dword que ya existan (Unity PlayerPrefs)
  lines una opción por línea                        (GTA V commandline.txt)
"""
import os
import re

from .ini import IniFile


class TextFile:
    def __init__(self, path):
        self.path = path
        self.newline = "\r\n"
        self.encoding = "utf-8"
        self.lines = []
        self.exists = os.path.exists(path)
        if self.exists:
            raw = open(path, "rb").read()
            self.bom = raw.startswith(b"\xef\xbb\xbf")
            if self.bom:
                raw = raw[3:]
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                text, self.encoding = raw.decode("cp1252", errors="replace"), "cp1252"
            self.newline = "\r\n" if "\r\n" in text else "\n"
            self.lines = text.replace("\r\n", "\n").split("\n")
            if self.lines and self.lines[-1] == "":
                self.lines.pop()
        else:
            self.bom = False

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".kt-tmp"
        with open(tmp, "wb") as fh:
            if self.bom:
                fh.write(b"\xef\xbb\xbf")
            fh.write((self.newline.join(self.lines) + self.newline).encode(self.encoding, errors="replace"))
        mode = os.stat(self.path).st_mode if os.path.exists(self.path) else None
        os.replace(tmp, self.path)
        if mode is not None:
            os.chmod(self.path, mode | 0o200)


# --------------------------------------------------------------------------- call: Name(args)
class CallFile(TextFile):
    def set(self, name, args):
        pat = re.compile(rf"^\s*{re.escape(name)}\s*\(", re.I)
        for i, line in enumerate(self.lines):
            if pat.match(line):
                if args is None:
                    del self.lines[i]
                else:
                    indent = line[:len(line) - len(line.lstrip())]
                    self.lines[i] = f"{indent}{name}({args})"
                return
        if args is not None:
            self.lines.append(f"{name}({args})")

    def get(self, name):
        pat = re.compile(rf"^\s*{re.escape(name)}\s*\((.*)\)", re.I)
        for line in self.lines:
            m = pat.match(line)
            if m:
                return m.group(1)
        return None


# --------------------------------------------------------------------------- kv: Key = "value" // comment
class KvFile(TextFile):
    LINE = re.compile(r'^(\s*)([^\s=;/#]+)(\s*[=:]\s*)("?)([^"/\r\n]*?)("?)(\s*(?://|;).*)?$')

    def set(self, key, value, only_existing=False, quote=None):
        for i, line in enumerate(self.lines):
            m = self.LINE.match(line)
            if m and m.group(2).lower() == key.lower():
                if value is None:
                    del self.lines[i]
                    return True
                q = m.group(4) if quote is None else ('"' if quote else "")
                self.lines[i] = f'{m.group(1)}{m.group(2)}{m.group(3)}{q}{value}{q}{m.group(7) or ""}'
                return True
        if value is not None and not only_existing:
            q = '"' if quote else ""
            self.lines.append(f"{key} = {q}{value}{q}")
            return True
        return False

    def get(self, key):
        for line in self.lines:
            m = self.LINE.match(line)
            if m and m.group(2).lower() == key.lower():
                return m.group(5)
        return None


# --------------------------------------------------------------------------- cfg: comando valor
class CfgFile(TextFile):
    def set(self, cmd, value):
        pat = re.compile(rf"^\s*{re.escape(cmd)}(\s|$)", re.I)
        for i, line in enumerate(self.lines):
            if pat.match(line):
                if value is None:
                    del self.lines[i]
                else:
                    self.lines[i] = f"{cmd} {value}"
                return
        if value is not None:
            self.lines.append(f"{cmd} {value}")

    def get(self, cmd):
        pat = re.compile(rf'^\s*{re.escape(cmd)}\s+"?([^"\s]*)', re.I)
        for line in self.lines:
            m = pat.match(line)
            if m:
                return m.group(1)
        return None


# --------------------------------------------------------------------------- lines: una opción por línea
class LinesFile(TextFile):
    def set(self, line, present=True):
        found = [i for i, existing in enumerate(self.lines) if existing.strip().lower() == line.strip().lower()]
        if present and not found:
            self.lines.append(line)
        if not present:
            for i in reversed(found):
                del self.lines[i]


# --------------------------------------------------------------------------- reg: registro de Wine
class RegFile(TextFile):
    """Solo cambia valores dword que ya existen. Las claves de Unity llevan un sufijo _h<número>,
    así que se buscan por prefijo ("OptionsGfxSSAO" -> "OptionsGfxSSAO_h12345")."""

    def _section_range(self, section):
        want = "[" + section.replace("\\", "\\\\").lower() + "]"
        start = None
        for i, line in enumerate(self.lines):
            if line.startswith("["):
                if start is not None:
                    return start, i
                head = line.split("]")[0] + "]"
                if head.lower() == want:
                    start = i
        return (start, len(self.lines)) if start is not None else None

    def set(self, section, prefix, value):
        rng = self._section_range(section)
        if not rng:
            return False
        pat = re.compile(rf'^"({re.escape(prefix)}(?:_h\d+)?)"=dword:([0-9a-fA-F]{{8}})$', re.I)
        done = False
        for i in range(rng[0] + 1, rng[1]):
            m = pat.match(self.lines[i])
            if m:
                self.lines[i] = f'"{m.group(1)}"=dword:{int(value) & 0xffffffff:08x}'
                done = True
        return done

    def get(self, section, prefix):
        rng = self._section_range(section)
        if not rng:
            return None
        pat = re.compile(rf'^"{re.escape(prefix)}(?:_h\d+)?"=dword:([0-9a-fA-F]{{8}})$', re.I)
        for i in range(rng[0] + 1, rng[1]):
            m = pat.match(self.lines[i])
            if m:
                return int(m.group(1), 16)
        return None


# --------------------------------------------------------------------------- xml: <Elemento value="x"/>
class XmlFile(TextFile):
    """Edición textual de atributos value="..." por ruta (p. ej. "graphics/TextureQuality").
    No reescribe el XML entero: así no se pierde nada que el juego espere tal cual."""

    def _find(self, path):
        parts = path.split("/")
        depth_target = len(parts)
        stack = []
        for i, line in enumerate(self.lines):
            for m in re.finditer(r"<(/?)([A-Za-z_][\w.\-]*)([^>]*?)(/?)>", line):
                closing, name, selfclose = m.group(1), m.group(2), m.group(4)
                if closing:
                    if stack and stack[-1] == name:
                        stack.pop()
                    continue
                stack.append(name)
                tail = stack[-depth_target:]
                if len(stack) >= depth_target and [t.lower() for t in tail] == [p.lower() for p in parts]:
                    return i, m
                if selfclose:
                    stack.pop()
        return None

    def set(self, path, value):
        hit = self._find(path)
        if not hit:
            return False
        i, m = hit
        tag = m.group(0)
        if re.search(r'\bvalue="[^"]*"', tag):
            new = re.sub(r'\bvalue="[^"]*"', f'value="{value}"', tag, count=1)
        else:
            return False
        line = self.lines[i]
        self.lines[i] = line[:m.start()] + new + line[m.end():]
        return True

    def get(self, path):
        hit = self._find(path)
        if not hit:
            return None
        v = re.search(r'\bvalue="([^"]*)"', hit[1].group(0))
        return v.group(1) if v else None


def open_editor(kind, path):
    return {"ini": IniFile, "xml": XmlFile, "call": CallFile, "kv": KvFile, "cfg": CfgFile,
            "reg": RegFile, "lines": LinesFile}[kind](path)
