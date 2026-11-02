import { ButtonItem, Field, PanelSection, PanelSectionRow, ToggleField } from "@decky/ui";
import { callable, toaster } from "@decky/api";
import { useEffect, useState } from "react";
import { t } from "./i18n";

interface ModsStatus {
  ok?: boolean;
  error?: string;
  detail?: string;
  installed: boolean;
  version?: string | null;
  bundled?: string | null;
  service: boolean;
  port?: number;
  pin?: string | null;
  paired?: number;
  nexus_key?: boolean;
  url?: string;
  qr?: string | null;
  addresses?: { iface: string; ip: string }[];
}

const modsStatus = callable<[], ModsStatus>("mods_status");
const modsInstall = callable<[], ModsStatus>("mods_install");
const modsUninstall = callable<[], ModsStatus>("mods_uninstall");
const modsService = callable<[on: boolean], ModsStatus>("mods_service");
const modsNewPin = callable<[], ModsStatus>("mods_newpin");

function explain(r: ModsStatus, fallback: string): string {
  const known = r.error ? t.modsErrors[r.error] : undefined;
  const base = known ?? r.error ?? fallback;
  return r.detail ? `${base}: ${r.detail}` : base;
}

export function ModsSection() {
  const [st, setSt] = useState<ModsStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async () => setSt(await modsStatus());

  useEffect(() => {
    load();
  }, []);

  const run = async (fn: () => Promise<ModsStatus>, okMsg: string, failMsg: string) => {
    setBusy(true);
    setError(null);
    try {
      const r = await fn();
      setSt(r);
      if (r.ok === false) {
        setError(explain(r, failMsg));
        toaster.toast({ title: t.modsTitle, body: failMsg });
      } else {
        toaster.toast({ title: t.modsTitle, body: okMsg });
      }
    } finally {
      setBusy(false);
    }
  };

  if (!st) {
    return (
      <PanelSection>
        <PanelSectionRow>
          <Field label={t.loading} />
        </PanelSectionRow>
      </PanelSection>
    );
  }

  if (!st.installed) {
    return (
      <PanelSection>
        <PanelSectionRow>
          <Field description={t.modsNotInstalled} />
        </PanelSectionRow>
        {error && (
          <PanelSectionRow>
            <Field description={`⚠️ ${error}`} />
          </PanelSectionRow>
        )}
        <PanelSectionRow>
          <ButtonItem
            layout="below"
            disabled={busy}
            onClick={() => run(modsInstall, t.modsInstalled, t.modsInstallFail)}
          >
            {busy ? t.modsInstalling : t.modsInstall}
          </ButtonItem>
        </PanelSectionRow>
      </PanelSection>
    );
  }

  const needsUpdate = !!st.bundled && !!st.version && st.bundled !== st.version;
  const ips = (st.addresses ?? []).map((a) => ({ ...a, url: `http://${a.ip}:${st.port ?? 8765}/` }));

  return (
    <PanelSection>
      <PanelSectionRow>
        <Field label={t.modsVersion}>{st.version ?? "?"}</Field>
      </PanelSectionRow>
      <PanelSectionRow>
        <ToggleField
          label={t.modsServer}
          description={t.modsServerDesc}
          checked={st.service}
          disabled={busy}
          onChange={(on) =>
            run(() => modsService(on), t.modsServer, t.modsInstallFail)
          }
        />
      </PanelSectionRow>
      {error && (
        <PanelSectionRow>
          <Field description={`⚠️ ${error}`} />
        </PanelSectionRow>
      )}
      {st.service && (
        <>
          {ips.map((a) => (
            <PanelSectionRow key={a.iface + a.ip}>
              <Field label={`${t.modsOpen} (${a.iface})`} childrenLayout="below">
                {a.url}
              </Field>
            </PanelSectionRow>
          ))}
          <PanelSectionRow>
            <Field label={t.modsPin}>{st.pin}</Field>
          </PanelSectionRow>
          {st.qr && (
            <PanelSectionRow>
              <Field description={t.modsQr} childrenLayout="below">
                <img src={st.qr} style={{ width: "100%", maxWidth: 220, background: "#fff" }} />
              </Field>
            </PanelSectionRow>
          )}
        </>
      )}
      <PanelSectionRow>
        <Field label={t.modsNexus} description={st.nexus_key ? undefined : t.modsNexusNo}>
          {st.nexus_key ? t.modsNexusYes : t.no}
        </Field>
      </PanelSectionRow>
      <PanelSectionRow>
        <Field label={t.modsPaired}>{String(st.paired ?? 0)}</Field>
      </PanelSectionRow>
      <PanelSectionRow>
        <Field description={t.modsFirst} />
      </PanelSectionRow>
      {needsUpdate && (
        <PanelSectionRow>
          <ButtonItem
            layout="below"
            disabled={busy}
            onClick={() => run(modsInstall, t.modsInstalled, t.modsInstallFail)}
          >
            {`${t.modsUpdate} (${st.bundled})`}
          </ButtonItem>
        </PanelSectionRow>
      )}
      <PanelSectionRow>
        <ButtonItem layout="below" disabled={busy} onClick={() => run(modsNewPin, t.modsPin, t.modsInstallFail)}>
          {t.modsNewPin}
        </ButtonItem>
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" disabled={busy} onClick={() => run(modsUninstall, t.modsUninstall, t.modsInstallFail)}>
          {t.modsUninstall}
        </ButtonItem>
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" disabled={busy} onClick={load}>
          {t.refresh}
        </ButtonItem>
      </PanelSectionRow>
    </PanelSection>
  );
}
