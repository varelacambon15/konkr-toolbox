import { ButtonItem, DropdownItem, Field, Navigation, PanelSection, PanelSectionRow, Router, TextField } from "@decky/ui";
import { callable, toaster } from "@decky/api";
import { useEffect, useState } from "react";
import { t } from "./i18n";

interface VdfFile {
  path: string;
  name: string;
  folder: string;
  title: string;
  ctype: string;
  installed: boolean;
}

interface Template {
  file: string;
  title: string;
  ctype: string;
}

interface MapsResult {
  ok: boolean;
  error?: string;
  files?: VdfFile[];
  templates?: Template[];
  games?: { appid: number; name: string }[];
  restored?: number;
  file?: string;
  title?: string;
}

const mapsList = callable<[], MapsResult>("maps_list");
const mapsInstall = callable<[path: string], MapsResult>("maps_install");
const mapsRemove = callable<[name: string], MapsResult>("maps_remove");

let lastAppid: number | null = null;
let lastPath: string | null = null;

function runningAppid(): number | null {
  try {
    const app = Router.MainRunningApp as any;
    return app ? Number(app.appid) : null;
  } catch {
    return null;
  }
}

/** Abre la configuración del mando de un juego (cierra antes el menú de acceso rápido). */
function openConfigurator(appid: number): boolean {
  try {
    Navigation.CloseSideMenus();
  } catch {
    /* nada */
  }
  try {
    SteamClient.Apps.ShowControllerConfigurator(appid);
    return true;
  } catch {
    try {
      (SteamClient as any).URL.ExecuteSteamURL(`steam://controllerconfig/${appid}`);
      return true;
    } catch {
      return false;
    }
  }
}

export function MapsSection() {
  const [data, setData] = useState<MapsResult | null>(null);
  const [appid, setAppid] = useState<number | null>(null);
  const [path, setPath] = useState<string | null>(null);
  const [tpl, setTpl] = useState<string | null>(null);
  const [pubId, setPubId] = useState("");
  const [busy, setBusy] = useState(false);
  const running = runningAppid();

  const load = async () => {
    setData(null);
    const r = await mapsList();
    setData(r);
    if (!r.ok) return;
    const games = r.games ?? [];
    const pickGame = [appid, running, lastAppid].find((id) => id != null && games.some((g) => g.appid === id));
    setAppid(pickGame ?? games[0]?.appid ?? null);
    const files = r.files ?? [];
    const pickFile = [path, lastPath].find((p) => p != null && files.some((f) => f.path === p));
    setPath(pickFile ?? files[0]?.path ?? null);
    setTpl(r.templates?.[0]?.file ?? null);
    if (r.restored) toaster.toast({ title: t.mapsTitle, body: `${t.mapsRestored}: ${r.restored}` });
  };

  useEffect(() => {
    load();
  }, []);

  if (data === null) {
    return (
      <PanelSection>
        <PanelSectionRow>
          <Field label={t.mapsSearching} />
        </PanelSectionRow>
      </PanelSection>
    );
  }

  if (!data.ok) {
    return (
      <PanelSection>
        <PanelSectionRow>
          <Field description={data.error === "no-steam" ? t.vcErrors["no-steam"] : `${t.ktError}: ${data.error}`} />
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={load}>
            {t.refresh}
          </ButtonItem>
        </PanelSectionRow>
      </PanelSection>
    );
  }

  const games = data.games ?? [];
  const files = data.files ?? [];
  const templates = data.templates ?? [];
  const game = games.find((g) => g.appid === appid);
  const file = files.find((f) => f.path === path);

  const install = async (thenApply: boolean) => {
    if (!file) return;
    setBusy(true);
    try {
      const r = await mapsInstall(file.path);
      if (!r.ok) {
        toaster.toast({ title: t.mapsTitle, body: r.error === "not-vdf" ? t.mapsNotVdf : `${t.ktError}: ${r.error}` });
        return;
      }
      if (thenApply && game) {
        const opened = openConfigurator(game.appid);
        toaster.toast({
          title: `${t.mapsInstalled}: ${r.title}`,
          body: opened ? t.mapsPickHint : t.mapsOpenFailed,
          duration: 8000,
        });
      } else {
        toaster.toast({ title: `${t.mapsInstalled}: ${r.title}`, body: t.mapsAllGames });
      }
      await load();
    } finally {
      setBusy(false);
    }
  };

  const applyId = () => {
    const id = pubId.replace(/\D/g, "");
    if (!game || !id) return;
    try {
      Navigation.CloseSideMenus();
    } catch {
      /* nada */
    }
    try {
      (SteamClient as any).URL.ExecuteSteamURL(`steam://controllerconfig/${game.appid}/${id}`);
      toaster.toast({ title: t.mapsTitle, body: t.mapsIdSent });
    } catch {
      toaster.toast({ title: t.mapsTitle, body: t.mapsOpenFailed });
    }
  };

  const remove = async () => {
    if (!tpl) return;
    setBusy(true);
    try {
      const r = await mapsRemove(tpl);
      toaster.toast({ title: t.mapsTitle, body: r.ok ? t.mapsRemoved : `${t.ktError}: ${r.error}` });
      await load();
    } finally {
      setBusy(false);
    }
  };

  return (
    <PanelSection>
      <PanelSectionRow>
        <Field description={t.mapsDesc} />
      </PanelSectionRow>

      {games.length > 0 && (
        <PanelSectionRow>
          <DropdownItem
            label={t.game}
            menuLabel={t.game}
            rgOptions={games.map((g) => ({
              data: g.appid,
              label: g.appid === running ? `▶ ${g.name} (${t.running})` : g.name,
            }))}
            selectedOption={appid}
            onChange={(o) => {
              lastAppid = Number(o.data);
              setAppid(lastAppid);
            }}
          />
        </PanelSectionRow>
      )}

      {files.length ? (
        <>
          <PanelSectionRow>
            <DropdownItem
              label={t.mapsFile}
              menuLabel={t.mapsFile}
              description={file ? `${file.folder}/${file.name}${file.ctype ? ` · ${file.ctype}` : ""}` : undefined}
              rgOptions={files.map((f) => ({ data: f.path, label: `${f.installed ? "✓ " : ""}${f.title}` }))}
              selectedOption={path}
              onChange={(o) => {
                lastPath = String(o.data);
                setPath(lastPath);
              }}
            />
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem layout="below" disabled={busy || !file || !game} onClick={() => install(true)}>
              {t.mapsApply}
            </ButtonItem>
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem layout="below" disabled={busy || !file} onClick={() => install(false)}>
              {t.mapsInstall}
            </ButtonItem>
          </PanelSectionRow>
        </>
      ) : (
        <PanelSectionRow>
          <Field description={t.mapsNone} />
        </PanelSectionRow>
      )}

      <PanelSectionRow>
        <ButtonItem layout="below" disabled={busy} onClick={load}>
          {t.mapsRescan}
        </ButtonItem>
      </PanelSectionRow>

      <PanelSectionRow>
        <TextField
          label={t.mapsIdLabel}
          description={t.mapsIdDesc}
          value={pubId}
          mustBeNumeric
          onChange={(e) => setPubId(e.target.value)}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" disabled={busy || !game || !pubId.replace(/\D/g, "")} onClick={applyId}>
          {t.mapsIdApply}
        </ButtonItem>
      </PanelSectionRow>

      {templates.length > 0 && (
        <>
          <PanelSectionRow>
            <DropdownItem
              label={`${t.mapsTemplates} (${templates.length})`}
              menuLabel={t.mapsTemplates}
              rgOptions={templates.map((x) => ({ data: x.file, label: x.title }))}
              selectedOption={tpl}
              onChange={(o) => setTpl(String(o.data))}
            />
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem layout="below" disabled={busy || !tpl} onClick={remove}>
              {t.mapsRemove}
            </ButtonItem>
          </PanelSectionRow>
        </>
      )}
    </PanelSection>
  );
}
