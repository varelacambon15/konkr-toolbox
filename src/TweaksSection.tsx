import { ButtonItem, DropdownItem, Field, PanelSection, PanelSectionRow, Router } from "@decky/ui";
import { callable, toaster } from "@decky/api";
import { useEffect, useState } from "react";
import { t } from "./i18n";
import { ensureWrapper } from "./steam";

const MODES = ["max", "perf", "balanced", "quality", "battery"];

interface Game {
  appid: number;
  name: string;
  profile: boolean;
  profile_name: string | null;
  missing: string[];
  mode: string | null;
  pending: boolean;
  has_backup: boolean;
  wrapped: boolean;
}

interface KtResult {
  ok: boolean;
  error?: string;
  games?: Game[];
  deferred?: boolean;
  [k: string]: any;
}

const ktGames = callable<[], KtResult>("kt_games");
const ktApply = callable<[appid: number, mode: string, running: boolean], KtResult>("kt_apply");
const ktRestore = callable<[appid: number], KtResult>("kt_restore");

// El juego elegido se recuerda mientras Steam siga abierto
let lastAppid: number | null = null;

function runningAppid(): number | null {
  try {
    const app = Router.MainRunningApp as any;
    return app ? Number(app.appid) : null;
  } catch {
    return null;
  }
}

function errorText(e?: string): string {
  if (e === "not-installed") return t.ktMissing;
  if (e === "old-version") return t.ktOld;
  if (e === "no-steam") return t.ktNoSteam;
  return `${t.ktError}: ${e ?? "?"}`;
}

export function TweaksSection() {
  const [games, setGames] = useState<Game[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [appid, setAppid] = useState<number | null>(null);
  const [mode, setMode] = useState<string>("balanced");
  const [busy, setBusy] = useState(false);
  const running = runningAppid();

  const load = async (keep?: number | null) => {
    const r = await ktGames();
    if (!r.ok) {
      setError(errorText(r.error));
      setGames([]);
      return;
    }
    setError(null);
    const list = r.games ?? [];
    setGames(list);
    const pick =
      [keep, running, lastAppid].find((id) => id != null && list.some((g) => g.appid === id)) ??
      (list[0]?.appid ?? null);
    setAppid(pick);
    const g = list.find((x) => x.appid === pick);
    if (g) setMode(g.mode ?? "balanced");
  };

  useEffect(() => {
    load();
  }, []);

  const game = games?.find((g) => g.appid === appid);
  const isRunning = game != null && running === game.appid;

  const apply = async () => {
    if (!game) return;
    setBusy(true);
    try {
      const w = await ensureWrapper(game.appid, game.wrapped);
      if (w === "added") toaster.toast({ title: t.ktTitle, body: t.wrapperAdded });
      if (w === "failed") toaster.toast({ title: t.ktTitle, body: t.wrapperFailed });
      const r = await ktApply(game.appid, mode, isRunning);
      if (!r.ok) {
        toaster.toast({ title: t.ktTitle, body: errorText(r.error) });
      } else {
        toaster.toast({
          title: `${t.applied}: ${t.modes[mode]}`,
          body: r.deferred || isRunning ? t.appliedNext : game.name,
        });
      }
      await load(game.appid);
    } finally {
      setBusy(false);
    }
  };

  const restore = async () => {
    if (!game) return;
    setBusy(true);
    try {
      const r = await ktRestore(game.appid);
      toaster.toast({ title: t.ktTitle, body: r.ok ? `${t.restored}: ${game.name}` : errorText(r.error) });
      await load(game.appid);
    } finally {
      setBusy(false);
    }
  };

  if (games === null) {
    return (
      <PanelSection title={t.ktTitle}>
        <PanelSectionRow>
          <Field label={t.loading} />
        </PanelSectionRow>
      </PanelSection>
    );
  }

  if (error) {
    return (
      <PanelSection title={t.ktTitle}>
        <PanelSectionRow>
          <Field description={error} />
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={() => load()}>
            {t.refresh}
          </ButtonItem>
        </PanelSectionRow>
      </PanelSection>
    );
  }

  if (!games.length) {
    return (
      <PanelSection title={t.ktTitle}>
        <PanelSectionRow>
          <Field description={t.noGames} />
        </PanelSectionRow>
      </PanelSection>
    );
  }

  return (
    <PanelSection title={t.ktTitle}>
      <PanelSectionRow>
        <DropdownItem
          label={t.game}
          menuLabel={t.game}
          strDefaultLabel={t.game}
          rgOptions={games.map((g) => ({
            data: g.appid,
            label: g.appid === running ? `▶ ${g.name} (${t.running})` : g.name,
          }))}
          selectedOption={appid}
          onChange={(o) => {
            const id = Number(o.data);
            lastAppid = id;
            setAppid(id);
            const g = games.find((x) => x.appid === id);
            setMode(g?.mode ?? "balanced");
          }}
        />
      </PanelSectionRow>
      {game && (
        <>
          <PanelSectionRow>
            <Field
              label={t.profile}
              description={game.profile ? (game.missing.length ? t.missingFiles : undefined) : undefined}
            >
              {game.profile ? game.profile_name : t.noProfile}
            </Field>
          </PanelSectionRow>
          <PanelSectionRow>
            <Field label={t.currentMode} description={game.pending ? t.pending : undefined}>
              {game.mode ? t.modes[game.mode] ?? game.mode : t.none}
            </Field>
          </PanelSectionRow>
          <PanelSectionRow>
            <DropdownItem
              label={t.mode}
              menuLabel={t.mode}
              description={t.hints[mode]}
              rgOptions={MODES.map((m) => ({ data: m, label: t.modes[m] }))}
              selectedOption={mode}
              onChange={(o) => setMode(String(o.data))}
            />
          </PanelSectionRow>
          {isRunning && (
            <PanelSectionRow>
              <Field description={t.runningNote} />
            </PanelSectionRow>
          )}
          <PanelSectionRow>
            <ButtonItem layout="below" disabled={busy} onClick={apply}>
              {t.apply}
            </ButtonItem>
          </PanelSectionRow>
          {(game.mode || game.has_backup) && (
            <PanelSectionRow>
              <ButtonItem layout="below" disabled={busy || isRunning} onClick={restore}>
                {t.restore}
              </ButtonItem>
            </PanelSectionRow>
          )}
        </>
      )}
    </PanelSection>
  );
}
