"""Editor de archivos INI que respeta el formato original (comentarios, orden, mayúsculas,
fin de línea). Pensado para los INI de Bethesda y Unreal, que no siempre son INI «estándar»."""
import os


class IniFile:
    def __init__(self, path):
        self.path = path
        self.newline = "\r\n"
        self.lines = []
        self.bom = False
        self.encoding = "utf-8"
        if os.path.exists(path):
            raw = open(path, "rb").read()
            if raw.startswith(b"\xef\xbb\xbf"):
                self.bom = True
                raw = raw[3:]
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                text = raw.decode("cp1252", errors="replace")
                self.encoding = "cp1252"
            self.newline = "\r\n" if "\r\n" in text else "\n"
            self.lines = text.replace("\r\n", "\n").split("\n")
            if self.lines and self.lines[-1] == "":
                self.lines.pop()

    # ---- búsqueda ------------------------------------------------------------
    def _sections(self):
        """[(nombre, índice_cabecera, índice_fin_exclusivo)]"""
        out, cur, start = [], None, 0
        for i, line in enumerate(self.lines):
            s = line.strip()
            if s.startswith("[") and s.endswith("]"):
                if cur is not None or i > 0:
                    out.append((cur, start, i))
                cur, start = s[1:-1].strip(), i
        out.append((cur, start, len(self.lines)))
        return out

    def _find_section(self, section):
        for name, start, end in self._sections():
            if name is not None and name.lower() == section.lower():
                return start, end
        return None

    def get(self, section, key, default=None):
        sec = self._find_section(section)
        if not sec:
            return default
        for i in range(sec[0] + 1, sec[1]):
            k, v = self._split(self.lines[i])
            if k is not None and k.lower() == key.lower():
                return v
        return default

    @staticmethod
    def _split(line):
        s = line.strip()
        if not s or s[0] in ";#[" or "=" not in s:
            return None, None
        k, v = s.split("=", 1)
        return k.strip(), v.strip()

    # ---- cambios ---------------------------------------------------------------
    def set(self, section, key, value):
        value = str(value)
        sec = self._find_section(section)
        if not sec:
            if self.lines and self.lines[-1].strip():
                self.lines.append("")
            self.lines += [f"[{section}]", f"{key}={value}"]
            return
        last_kv = sec[0]
        for i in range(sec[0] + 1, sec[1]):
            k, _v = self._split(self.lines[i])
            if k is not None:
                last_kv = i
                if k.lower() == key.lower():
                    self.lines[i] = f"{k}={value}"
                    return
        self.lines.insert(last_kv + 1, f"{key}={value}")

    def remove(self, section, key):
        sec = self._find_section(section)
        if not sec:
            return
        for i in range(sec[0] + 1, sec[1]):
            k, _v = self._split(self.lines[i])
            if k is not None and k.lower() == key.lower():
                del self.lines[i]
                return

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        data = self.newline.join(self.lines) + self.newline
        tmp = self.path + ".kt-tmp"
        with open(tmp, "wb") as fh:
            if self.bom:
                fh.write(b"\xef\xbb\xbf")
            fh.write(data.encode(self.encoding, errors="replace"))
        os.replace(tmp, self.path)
