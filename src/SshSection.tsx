import { ButtonItem, Field, PanelSection, PanelSectionRow, ToggleField } from "@decky/ui";
import { callable, toaster } from "@decky/api";
import { useEffect, useState } from "react";
import { t } from "./i18n";

interface SshStatus {
  ok?: boolean;
  installed: boolean;
  active: boolean;
  enabled: boolean;
  state: string;
  port: string;
  addresses: { iface: string; ip: string }[];
  wifi: string | null;
  hostname: string;
  user: string;
  password: boolean | null;
}

const sshStatus = callable<[], SshStatus>("ssh_status");
const sshSet = callable<[on: boolean], SshStatus>("ssh_set");

export function SshSection() {
  const [st, setSt] = useState<SshStatus | null>(null);
  const [busy, setBusy] = useState(false);

  const load = async () => setSt(await sshStatus());

  useEffect(() => {
    load();
  }, []);

  const toggle = async (on: boolean) => {
    setBusy(true);
    try {
      const r = await sshSet(on);
      setSt(r);
      toaster.toast({ title: t.sshTitle, body: r.ok ? (r.active ? t.sshOn : t.sshOff) : t.sshFail });
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
          <Field description={t.sshMissing} />
        </PanelSectionRow>
      </PanelSection>
    );
  }

  const ip = st.addresses.find((a) => a.iface.startsWith("wl"))?.ip ?? st.addresses[0]?.ip;
  const port = st.port.split(",")[0].trim();

  return (
    <PanelSection>
      <PanelSectionRow>
        <ToggleField
          label={t.sshEnabled}
          description={t.sshDesc}
          checked={st.active}
          disabled={busy}
          onChange={toggle}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <Field label={t.status}>{st.state}</Field>
      </PanelSectionRow>
      <PanelSectionRow>
        <Field label={t.startsOnBoot}>{st.enabled ? t.yes : t.no}</Field>
      </PanelSectionRow>
      {st.addresses.length ? (
        st.addresses.map((a) => (
          <PanelSectionRow key={a.iface + a.ip}>
            <Field label={`${t.ip} (${a.iface})`}>{a.ip}</Field>
          </PanelSectionRow>
        ))
      ) : (
        <PanelSectionRow>
          <Field label={t.ip}>{t.noIp}</Field>
        </PanelSectionRow>
      )}
      {st.wifi && (
        <PanelSectionRow>
          <Field label={t.wifi}>{st.wifi}</Field>
        </PanelSectionRow>
      )}
      <PanelSectionRow>
        <Field label={t.port}>{st.port}</Field>
      </PanelSectionRow>
      <PanelSectionRow>
        <Field label={t.user}>{st.user}</Field>
      </PanelSectionRow>
      <PanelSectionRow>
        <Field label={t.host}>{st.hostname}</Field>
      </PanelSectionRow>
      {ip && st.active && (
        <PanelSectionRow>
          <Field label={t.connect} childrenLayout="below" description={t.dynamicIp}>
            {`sftp://${st.user}@${ip}${port && port !== "22" ? ":" + port : ""}`}
          </Field>
        </PanelSectionRow>
      )}
      {st.password === false && (
        <PanelSectionRow>
          <Field description={`⚠️ ${t.noPassword}`} />
        </PanelSectionRow>
      )}
      <PanelSectionRow>
        <ButtonItem layout="below" disabled={busy} onClick={load}>
          {t.refresh}
        </ButtonItem>
      </PanelSectionRow>
    </PanelSection>
  );
}
