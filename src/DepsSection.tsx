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

const depsGames = callable<[], VcResult>("deps_games");
const depsInstall = callable<[appid: number, dep: string, variant: string], VcResult>("deps_install");

// Catálogo de dependencias. Para añadir una: aquí y en DEPS de py_modules/ktb_deps.py.
const DEPS = [
  { id: "vcredist", label: () => t.depVc, variants: [
    { id: "arm64", label: () => t.vcArm64 },
    { id: "x64", label: () => t.vcX64 },
    { id: "x86", label: () => t.vcX86 },
  ] },
];

let lastAppid: number | null = null;
let lastArch = "x64";
let lastDep = "vcredist";

export function DepsSection() {
  const [games, setGames] = useState<VcGame[] | null>(null);
  const [appid, setAppid] = useState<number | null>(null);
  const [arch, setArch] = useState(lastArch);
  const [dep, setDep] = useState(lastDep);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      const r = await depsGames();
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
      const r = await depsInstall(game.appid, dep, arch);
      let text: string;
      if (r.ok) {
        text = r.status === "already" ? t.vcAlready : r.status === "reboot" ? t.vcReboot : t.vcOk;
      } else {
        const base = t.vcErrors[r.status === "failed" ? "failed" : r.error ?? ""] ?? r.error ?? "?";
        text = `${base}${r.code != null ? ` (${r.code})` : ""}${r.detail ? `: ${r.detail}` : ""}`;
        if (r.log) text += ` — ${t.vcLog}: ${r.log}`;
      }
      setMsg(text);
      toaster.toast({ title: t.depsTitle, body: r.ok ? `${text}: ${game.name}` : text });
    } finally {
      setBusy(false);
    }
  };

  if (games === null) {
    return (
      <PanelSection>
        <PanelSectionRow>
          <Field label={t.loading} />
        </PanelSectionRow>
      </PanelSection>
    );
  }

  return (
    <PanelSection>
      {!games.length ? (
        <PanelSectionRow>
          <Field description={msg ?? t.vcNoGames} />
        </PanelSectionRow>
      ) : (
        <>
          <PanelSectionRow>
            <Field description={t.depsDesc} />
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
              label={t.depWhat}
              menuLabel={t.depWhat}
              rgOptions={DEPS.map((d) => ({ data: d.id, label: d.label() }))}
              selectedOption={dep}
              onChange={(o) => {
                lastDep = String(o.data);
                setDep(lastDep);
              }}
            />
          </PanelSectionRow>
          <PanelSectionRow>
            <DropdownItem
              label={t.vcArch}
              menuLabel={t.vcArch}
              rgOptions={(DEPS.find((d) => d.id === dep) ?? DEPS[0]).variants.map((v) => ({ data: v.id, label: v.label() }))}
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
