"""kt-run: lanzador que Steam ejecuta delante del juego (opciones de lanzamiento:
"~/.local/bin/kt-run %command%"). Lee los ajustes del juego y arranca el comando con ellos.
No debe fallar nunca: si algo va mal, arranca el juego sin tocar nada."""
import os
import re
import sys
import time


def appid_from(argv, env):
    for var in ("SteamAppId", "SteamGameId", "STEAM_COMPAT_APP_ID"):
        v = env.get(var, "")
        if v.isdigit() and v != "0":
            return int(v)
    for a in argv:
        m = re.match(r"AppId=(\d+)", a)
        if m:
            return int(m.group(1))
    return None


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("kt-run: úsalo en las opciones de lanzamiento de Steam: ~/.local/bin/kt-run %command%",
              file=sys.stderr)
        return 2
    env = dict(os.environ)
    cmd = argv
    try:
        from . import settings
        appid = appid_from(argv, env)
        if appid:
            try:   # modo elegido con el juego abierto (p. ej. desde Konkr Toolbox)
                if settings.game_state(appid).get("pending"):
                    from . import optimize
                    optimize.apply_pending(appid)
            except Exception as e:  # noqa
                print(f"kt-run: modo pendiente no aplicado ({e})", file=sys.stderr)
            eff = settings.launch_settings(appid)
            extra_env, prefix, extra_args = settings.build_launch(eff)
            if prefix and all(__import__("shutil").which(p) for p in prefix[:1]):
                cmd = prefix + cmd
            env.update(extra_env)
            cmd = cmd + extra_args
            cores = None
            try:   # «Solo núcleos rápidos»: lo heredan Proton y el juego
                cores = settings.cpu_affinity(eff)
                if cores:
                    os.sched_setaffinity(0, cores)
            except (OSError, AttributeError) as e:
                print(f"kt-run: núcleos no limitados ({e})", file=sys.stderr)
                cores = None
            try:
                os.makedirs(settings.STATE_DIR, exist_ok=True)
                with open(os.path.join(settings.STATE_DIR, "last-launch.txt"), "w", encoding="utf-8") as f:
                    f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  appid={appid}\n")
                    for k, v in sorted(extra_env.items()):
                        f.write(f"{k}={v}\n")
                    f.write("args: " + " ".join(extra_args) + "\n")
                    if cores:
                        f.write("cpu: " + ",".join(str(c) for c in sorted(cores)) + "\n")
            except OSError:
                pass
    except Exception as e:  # noqa — el juego tiene que arrancar sí o sí
        print(f"kt-run: ajustes ignorados ({e})", file=sys.stderr)
        cmd, env = argv, dict(os.environ)
    os.execvpe(cmd[0], cmd, env)


if __name__ == "__main__":
    sys.exit(main())
