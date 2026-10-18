import { ButtonItem, DropdownItem, Field, PanelSection, PanelSectionRow } from "@decky/ui";
import { callable, toaster } from "@decky/api";
import { useEffect, useState } from "react";
import { t } from "./i18n";

interface VcGame {
  appid: number;
  name: string;
  proton: string | null;
}

interface VcResult {
  ok: boolean;
  error?: string;
  detail?: string;
  games?: VcGame[];
  status?: string;
  code?: number;
  proton?: string;
  log?: string;
  tail?: string;
}

const vcGames = callable<[], VcResult>("vc_games");
const vcInstall = callable<[appid: number, arch: string], VcResult>("vc_install");

let lastAppid: number | null = null;
let lastArch = "arm64";

export function VcSection() {
  const [games, setGames] = useState<VcGame[] | null>(null);
  const [appid, setAppid] = useState<number | null>(null);
  const [arch, setArch] = useState(lastArch);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      const r = await vcGames();
      const list = r.ok ? r.games ?? [] : [];
      setGames(list);
      if (!r.ok) setMsg(t.vcErrors[r.error ?? ""] ?? r.error ?? "?");
      setAppid(list.some((g) => g.appid === lastAppid) ? lastAppid : list[0]?.appid ?? null);
    })();
  }, []);

  const game = games?.find((g) => g.appid === appid);

  const install = async () => {
    if (!game) return;
    setBusy(true);
    setMsg(t.vcInstalling);
    try {
      const r = await vcInstall(game.appid, arch);
      let text: string;
      if (r.ok) {
        text = r.status === "already" ? t.vcAlready : r.status === "reboot" ? t.vcReboot : t.vcOk;
      } else {
        const base = t.vcErrors[r.status === "failed" ? "failed" : r.error ?? ""] ?? r.error ?? "?";
        text = `${base}${r.code != null ? ` (${r.code})` : ""}${r.detail ? `: ${r.detail}` : ""}`;
        if (r.log) text += ` — ${t.vcLog}: ${r.log}`;
      }
      setMsg(text);
      toaster.toast({ title: t.vcTitle, body: r.ok ? `${text}: ${game.name}` : text });
    } finally {
      setBusy(false);
    }
  };

  if (games === null) {
    return (
      <PanelSection title={t.vcTitle}>
        <PanelSectionRow>
          <Field label={t.loading} />
        </PanelSectionRow>
      </PanelSection>
    );
  }

  return (
    <PanelSection title={t.vcTitle}>
      {!games.length ? (
        <PanelSectionRow>
          <Field description={msg ?? t.vcNoGames} />
        </PanelSectionRow>
      ) : (
        <>
          <PanelSectionRow>
            <Field description={t.vcDesc} />
          </PanelSectionRow>
          <PanelSectionRow>
            <DropdownItem
              label={t.vcGame}
              menuLabel={t.vcGame}
              rgOptions={games.map((g) => ({ data: g.appid, label: g.name }))}
              selectedOption={appid}
              onChange={(o) => {
                lastAppid = Number(o.data);
                setAppid(lastAppid);
                setMsg(null);
              }}
            />
          </PanelSectionRow>
          {game?.proton && (
            <PanelSectionRow>
              <Field label={t.vcProton}>{game.proton}</Field>
            </PanelSectionRow>
          )}
          <PanelSectionRow>
            <DropdownItem
              label={t.vcArch}
              menuLabel={t.vcArch}
              rgOptions={[
                { data: "arm64", label: t.vcArm64 },
                { data: "x64", label: t.vcX64 },
                { data: "x86", label: t.vcX86 },
              ]}
              selectedOption={arch}
              onChange={(o) => {
                lastArch = String(o.data);
                setArch(lastArch);
              }}
            />
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem layout="below" disabled={busy || !game} onClick={install}>
              {busy ? t.vcInstalling : t.vcInstall}
            </ButtonItem>
          </PanelSectionRow>
          {msg && !busy && (
            <PanelSectionRow>
              <Field description={msg} />
            </PanelSectionRow>
          )}
        </>
      )}
    </PanelSection>
  );
}
