# Componentes de terceros incluidos

El control remoto (sección "Control remoto") incluye estas piezas sin modificar:

- **noVNC 1.7.0** (`static/novnc/`): cliente VNC en JavaScript. Licencia MPL-2.0 (ver `static/novnc/LICENSE.txt`).
  Origen: paquete npm `@novnc/novnc`.
- **websockify 0.13.0** (`py_modules/vendor/websockify/`): puente WebSocket a TCP. Licencia LGPL-3.0
  (ver `py_modules/vendor/websockify/COPYING`). Origen: paquete PyPI `websockify`.

`x11vnc` NO se incluye: es un programa del sistema que debe estar instalado en la consola.

## Konkr Mod Manager (modmanager/)
Código propio del autor (MIT). Incluye `qrcodegen.py` de Project Nayuki (MIT).
