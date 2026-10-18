import { ButtonItem, DropdownItem, Field, PanelSectionRow, ToggleField } from "@decky/ui";
import { callable, toaster } from "@decky/api";
import { Fragment, useEffect, useState } from "react";
import { langCode, t } from "./i18n";
import { ensureWrapper } from "./steam";

interface Opt {
  key: string;
  kind: "bool" | "choice";
  group: string;
  group_label: string;
  label: string;
  hint: string;
  avail: boolean;
  value: any;
  choices: { value: any; label: string }[];
}

interface OptsResult {
  ok: boolean;
  error?: string;
  custom?: boolean;
  options?: Opt[];
}

const ktOpts = callable<[appid: number, lang: string], OptsResult>("kt_opts");
const ktSetOpt = callable<[appid: number, key: string, value: string, lang: string], OptsResult>("kt_set_opt");

// Si el desplegable estaba abierto, se recuerda mientras Steam siga en marcha
let openState = false;

function errText(e?: string): string {
  if (e === "bad-command" || e === "old-version") return t.optsOld;
  if (e === "not-installed") return t.ktMissing;
  return `${t.ktError}: ${e ?? "?"}`;
}

/** Opciones de lanzamiento de un juego (catálogo de Konkr Tweaks), detrás de un botón. */
export function LaunchOptions({ appid, wrapped, onChanged }: { appid: number; wrapped: boolean; onChanged?: () => void }) {
  const [open, setOpen] = useState(openState);
  const [opts, setOpts] = useState<Opt[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    let alive = true;
    setOpts(null);
    setError(null);
    ktOpts(appid, langCode).then((r) => {
      if (!alive) return;
      if (r.ok) setOpts(r.options ?? []);
      else setError(errText(r.error));
    });
    return () => {
      alive = false;
    };
  }, [open, appid]);

  const change = async (o: Opt, value: any) => {
    setBusy(true);
    try {
      const w = await ensureWrapper(appid, wrapped);
      if (w === "added") toaster.toast({ title: t.ktTitle, body: t.wrapperAdded });
      if (w === "failed") toaster.toast({ title: t.ktTitle, body: t.wrapperFailed });
      const r = await ktSetOpt(appid, o.key, o.kind === "bool" ? (value ? "1" : "0") : String(value), langCode);
      if (r.ok) {
        setOpts(r.options ?? opts);
        toaster.toast({ title: o.label, body: t.optsSaved });
        onChanged?.();
      } else {
        toaster.toast({ title: o.label, body: errText(r.error) });
      }
    } finally {
      setBusy(false);
    }
  };

  let lastGroup = "";
  return (
    <>
      <PanelSectionRow>
        <ButtonItem
          layout="below"
          onClick={() => {
            openState = !open;
            setOpen(!open);
          }}
        >
          {open ? "▼" : "▶"} {t.optsTitle}
        </ButtonItem>
      </PanelSectionRow>
      {open && error && (
        <PanelSectionRow>
          <Field description={error} />
        </PanelSectionRow>
      )}
      {open && !error && opts === null && (
        <PanelSectionRow>
          <Field label={t.loading} />
        </PanelSectionRow>
      )}
      {open && opts && (
        <>
          <PanelSectionRow>
            <Field description={t.optsDesc} />
          </PanelSectionRow>
          {opts.map((o) => {
            const header = o.group !== lastGroup ? o.group_label : null;
            lastGroup = o.group;
            return (
              <Fragment key={o.key}>
                {header && (
                  <PanelSectionRow>
                    <Field label={<b>{header}</b>} />
                  </PanelSectionRow>
                )}
                <PanelSectionRow>
                  {o.kind === "bool" ? (
                    <ToggleField
                      label={o.label}
                      description={o.avail ? o.hint || undefined : t.optsUnavailable}
                      checked={!!o.value}
                      disabled={busy || !o.avail}
                      onChange={(v) => change(o, v)}
                    />
                  ) : (
                    <DropdownItem
                      label={o.label}
                      menuLabel={o.label}
                      description={o.hint || undefined}
                      disabled={busy || !o.avail}
                      rgOptions={o.choices.map((c) => ({ data: c.value, label: c.label }))}
                      selectedOption={o.value ?? o.choices[0]?.value}
                      onChange={(c) => change(o, c.data)}
                    />
                  )}
                </PanelSectionRow>
              </Fragment>
            );
          })}
        </>
      )}
    </>
  );
}
