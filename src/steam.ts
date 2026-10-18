// Opciones de lanzamiento de Steam desde el propio cliente (funciona con Steam abierto,
// a diferencia de editar localconfig.vdf, que exige cerrar Steam).
export const WRAPPER = "~/.local/bin/kt-run";

export function withWrapper(lo: string): string {
  const s = (lo || "").trim();
  if (s.includes("kt-run")) return s;
  if (s.includes("%command%")) return s.replace("%command%", `${WRAPPER} %command%`);
  return s ? `${WRAPPER} %command% ${s}` : `${WRAPPER} %command%`;
}

export function getLaunchOptions(appid: number): Promise<string | null> {
  return new Promise((resolve) => {
    let done = false;
    let reg: { unregister(): void } | undefined;
    const finish = (v: string | null) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      setTimeout(() => {
        try {
          reg?.unregister();
        } catch {
          /* nada */
        }
      }, 0);
      resolve(v);
    };
    const timer = setTimeout(() => finish(null), 2500);
    try {
      reg = SteamClient.Apps.RegisterForAppDetails(appid, (d: any) => finish(d?.strLaunchOptions ?? ""));
    } catch {
      finish(null);
    }
  });
}

export function setLaunchOptions(appid: number, lo: string): boolean {
  try {
    SteamClient.Apps.SetAppLaunchOptions(appid, lo);
    return true;
  } catch {
    return false;
  }
}

/** Añade kt-run si falta. Devuelve "added", "present" o "failed". */
export async function ensureWrapper(appid: number, wrappedOnDisk: boolean): Promise<"added" | "present" | "failed"> {
  const lo = await getLaunchOptions(appid);
  if (lo === null) return wrappedOnDisk ? "present" : "failed";
  if (lo.includes("kt-run")) return "present";
  return setLaunchOptions(appid, withWrapper(lo)) ? "added" : "failed";
}
