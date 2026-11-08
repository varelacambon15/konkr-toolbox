# Resumen de la sesión de Call of Duty: Ghosts (iw6-mod en la KONKR)

Hecho el 2026-11-08 a partir del resumen automático de la propia sesión (la del 2-3 de noviembre).
No contiene contraseñas.

## Objetivo
Jugar a Ghosts (copia propia) con IW6-Mod (AlterWare/IW6x) en la KONKR Pocket FIT (SteamOS ARM,
Proton ARM64 + FEX). Prioridad: Extinction y Squads (multijugador con progresión contra bots).
Da igual si es online u offline. Alejandro pidió trabajar con autonomía pero sin estropear el
juego ni Steam. Límite de uso diario: parar al 85 %.

## Reglas de seguridad (siguen vigentes)
- Solo lectura hasta que él diga «adelante». Respaldo con `~/iw6x-steamos/tools/respaldo_steam.sh` antes de tocar Steam.
- No tocar `shortcuts.vdf` a mano: los cambios de opciones de lanzamiento, desde la interfaz de Steam.
- No crear ni modificar archivos en la carpeta del juego salvo copias nuevas (incidente del bucle de Steam, 29-oct).
- Nada de `sudo`, `rm -rf` ni `pacman` sin permiso explícito. Cualquier cambio al exe, solo en una copia renombrada.
- No usar `pkill -f` / `pgrep -f` (coinciden con la propia línea de comandos): usar `pgrep -x iw6-mod-konkr.e` o PIDs.

## Estado
- El juego arranca con el exe parcheado `iw6-mod-konkr.exe` (corrige la caída en RVA 0x316F74, ordinal 700 de urlmon).
- `-multiplayer` se salta el lanzador HTML roto. La primera carga tarda 2-3 min (1-2 en modo juego).
- El mod `zz_offline_play` (v8) carga y abre la lista de servidores (se ven 8 de Extinction).
- Atajo de Steam `iw6-mod-konkr.exe` (appid 3545488426, gameID 15227756838050070528), Proton Experimental (ARM64).
- Opciones de lanzamiento ahora: `FEX_ENABLEAVX=1 FEX_SMCCHECKS=full strace -f -qq -e trace=sendto,sendmsg,recvmsg,recvfrom,connect -s 120 -o /home/steamos/respaldos-konkr/dev-logs/join.strace %command% -multiplayer`
- Objetivo: `FEX_ENABLEAVX=1 FEX_SMCCHECKS=full %command% -multiplayer` (quitar el strace; `FEX_ENABLEAVX` no ayuda y se puede quitar también).
- Un prefijo no vacío es necesario: `%command% -args` sin prefijo da exit 127. No poner `SteamAppId/SteamGameId` (logo de Steam eterno).
- Hay que probar en Modo Juego (gamescope): en Escritorio, Xwayland se cae al unirse a una partida (explicit sync).
- Pantalla negra hasta cambiar de ventana: la ventana de Wine arranca minimizada (WM_STATE Iconic); `tools/dev/despertar_ventana.py` (con DISPLAY=:1) la despierta.

## El bloqueo
Los flujos que dependen del emulador de Demonware (dentro del propio iw6-mod.exe) no terminan:
«Connecting to Online Services», partida privada, «Joining Game Session».
- Con strace: al unirse envía un `getInfo` (p. ej. a 135.125.189.198:5072), recibe un `infoResponse` válido
  (protocolo 1, shortversion 0.0.1, gametype aliens, mapname mp_alien_dlc3), y después no manda `getchallenge` ni `connect`.
- Solo hay sockets UDP 27016 y 3074; no hay TCP. El hilo de Demonware espera en `poll`.
- Hipótesis sin confirmar: (a) `connect_to_party()` espera a que acabe la sincronización de datos online (`Live_SyncOnlineDataFlags`, sugerido desde `party.cpp` de iw6x);
  (b) falla algún hook del emulador (DNS, socket, select, hilos, temporizadores) bajo Wine + FEX.
- Descartado: teoría de licencia de Steam (steam_api64 nunca se carga; SteamAppId ya probado).
- «Invalid connect data!» / «XUID doesn't match the certificate!» probablemente son del lado del servidor.
- Master server: `server.alterware.dev:20810` (UDP, `getservers IW6 1 full empty`).

## Archivos
- Repo `~/iw6x-steamos`: unos 11 commits locales SIN subir (la Konkr no tiene credenciales; hay que hacer `git push` a mano).
  Herramientas: `tools/ghosts_wrapper.sh`, `respaldo_steam.sh`, `parchear_iw6mod.py`, `lanzar_ghosts.sh`, `instalar_mod.sh`, `tools/dev/*`;
  mod en `mod/zz_offline_play/__init__.lua`; notas en `notes/` (hallazgos-mod-y-servidores.md, resumen-noche-2026-11-03.md…).
- Juego: `/run/media/steamos/SteamSD/SteamLibrary/juegos/Call-Of-Duty-Ghost-A/` (originales intactos; añadidos: `iw6-mod-konkr.exe`, `data/ui_scripts/zz_offline_play/`).
- Respaldos: `~/respaldos-konkr/` (Steam, ui_scripts, cfg, `dev-logs/re/main.asm` con el desensamblado de la sección `.main`, offset 0x261000, VMA 0x1502aa000).
- No usar `~/Downloads/ghosts_wrapper.sh` (escribe `steam_appid.txt` con ruta relativa: peligroso).
- Log de Steam: `~/steam-15227756838050070528.log` (≈166 MB, pendiente de borrar con su permiso).

## Siguiente paso acordado
1. Respaldo de Steam (hecho el 8-nov: `~/respaldos-konkr/20261108-113106`).
2. Quitar el strace de las opciones de lanzamiento (en Steam, no a mano).
3. Desensamblar el manejo de `infoResponse`/`connect` en `main.asm` (solo lectura): buscar «Invalid connect data!», «XUID doesn't match the certificate» y «Challenge…»; ver qué frena el `connect`.
4. Alternativas: servidor local (el mod trae `addbot`, `connect`, `xstartprivateparty`); probar el botón SQUADS (`SquadsModeButtonAction`), que no espera a Demonware.
5. Con `WINEDEBUG=-all,+timestamp,+winsock,+sync,+err` y `PROTON_LOG=1`; con el juego colgado, `ss -tanp` y `/proc/PID/task/*/wchan`.
6. Menores: borrar capturas de `~/Pictures` por nombre exacto; vigilar la temperatura (80-95 °C en el menú es normal).
