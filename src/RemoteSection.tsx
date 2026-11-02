import { ButtonItem, DropdownItem, Field, PanelSection, PanelSectionRow, ToggleField } from "@decky/ui";
import { callable, toaster } from "@decky/api";
import { useEffect, useState } from "react";
import { t } from "./i18n";

interface RemoteStatus {
  ok?: boolean;
  error?: string;
  detail?: string;
  active: boolean;
  password?: string;
  web_port?: number;
  display?: string;
  seconds_left?: number;
  addresses?: { iface: string; ip: string }[];
}

interface RemoteDiag {
  ok: boolean;
  displays: string[];
  gamescope: boolean;
  x11vnc: string | null;
  web: boolean;
}

const remoteStatus = callable<[], RemoteStatus>("remote_status");
const remoteStart = callable<[minutes: number], RemoteStatus>("remote_start");
const remoteStop = callable<[], RemoteStatus>("remote_stop");
const remoteDiag = callable<[], RemoteDiag>("remote_diag");

const MINUTES = [15, 30, 60, 120];

function explain(r: RemoteStatus): string {
  const known = r.error ? t.remoteErrors[r.error] : undefined;
  const base = known ?? r.error ?? t.remoteFail;
  return r.detail ? `${base}: ${r.detail}` : base;
}

export function RemoteSection() {
  const [st, setSt] = useState<RemoteStatus | null>(null);
  const [minutes, setMinutes] = useState(30);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [diag, setDiag] = useState<RemoteDiag | null>(null);

  const load = async () => setSt(await remoteStatus());

  useEffect(() => {
    load();
  }, []);

  // Mientras está activo, se refresca para ir viendo el tiempo que queda
  useEffect(() => {
    if (!st?.active) return;
    const id = setInterval(load, 15000);
    return () => clearInterval(id);
  }, [st?.active]);

  const toggle = async (on: boolean) => {
    setBusy(true);
    setError(null);
    try {
      const r = on ? await remoteStart(minutes) : await remoteStop();
      setSt(r);
      if (on && !r.ok) {
        setError(explain(r));
        toaster.toast({ title: t.remoteTitle, body: t.remoteFail });
      } else {
        toaster.toast({ title: t.remoteTitle, body: r.active ? t.remoteOn : t.remoteOff });
      }
    } finally {
      setBusy(false);
    }
  };

  const showDiag = async () => setDiag(await remoteDiag());

  if (!st) {
    return (
      <PanelSection>
        <PanelSectionRow>
          <Field label={t.loading} />
        </PanelSectionRow>
      </PanelSection>
    );
  }

  const left = Math.max(0, Math.ceil((st.seconds_left ?? 0) / 60));
  const port = st.web_port ?? 6080;

  return (
    <PanelSection>
      <PanelSectionRow>
        <ToggleField
          label={t.remoteEnabled}
          description={t.remoteDesc}
          checked={st.active}
          disabled={busy}
          onChange={toggle}
        />
      </PanelSectionRow>
      {!st.active && (
        <PanelSectionRow>
          <DropdownItem
            label={t.remoteMinutes}
            rgOptions={MINUTES.map((m) => ({ data: m, label: `${m} ${t.remoteMin}` }))}
            selectedOption={minutes}
            onChange={(o) => setMinutes(o.data)}
          />
        </PanelSectionRow>
      )}
      {error && (
        <PanelSectionRow>
          <Field description={`⚠️ ${error}`} />
        </PanelSectionRow>
      )}
      {st.active && (
        <>
          {(st.addresses ?? []).map((a) => (
            <PanelSectionRow key={a.iface + a.ip}>
              <Field label={`${t.remoteOpen} (${a.iface})`} childrenLayout="below">
                {`http://${a.ip}:${port}/`}
              </Field>
            </PanelSectionRow>
          ))}
          <PanelSectionRow>
            <Field label={t.remotePassword}>{st.password}</Field>
          </PanelSectionRow>
          <PanelSectionRow>
            <Field label={t.remoteLeft}>{`${left} ${t.remoteMin}`}</Field>
          </PanelSectionRow>
          <PanelSectionRow>
            <Field description={t.remoteWarn} />
          </PanelSectionRow>
        </>
      )}
      <PanelSectionRow>
        <ButtonItem layout="below" disabled={busy} onClick={showDiag}>
          {t.remoteDiag}
        </ButtonItem>
      </PanelSectionRow>
      {diag && (
        <>
          <PanelSectionRow>
            <Field label={t.remoteDiagDisplays}>{diag.displays.length ? diag.displays.join(", ") : t.remoteDiagNone}</Field>
          </PanelSectionRow>
          <PanelSectionRow>
            <Field label={t.remoteDiagGamescope}>{diag.gamescope ? t.yes : t.no}</Field>
          </PanelSectionRow>
          <PanelSectionRow>
            <Field label={t.remoteDiagX11vnc}>{diag.x11vnc ? t.yes : t.no}</Field>
          </PanelSectionRow>
          <PanelSectionRow>
            <Field label={t.remoteDiagWeb}>{diag.web ? t.yes : t.no}</Field>
          </PanelSectionRow>
        </>
      )}
      <PanelSectionRow>
        <ButtonItem layout="below" disabled={busy} onClick={load}>
          {t.refresh}
        </ButtonItem>
      </PanelSectionRow>
    </PanelSection>
  );
}
