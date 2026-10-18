import { ButtonItem, PanelSection, PanelSectionRow } from "@decky/ui";
import { ReactNode, useState } from "react";

// Qué secciones estaban abiertas, mientras Steam siga en marcha
const openState: Record<string, boolean> = {};

/** Una sección cerrada detrás de un botón. El contenido solo se carga al abrirla. */
export function Collapsible({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  const [open, setOpen] = useState(!!openState[id]);
  return (
    <>
      <PanelSection>
        <PanelSectionRow>
          <ButtonItem
            layout="below"
            onClick={() => {
              openState[id] = !open;
              setOpen(!open);
            }}
          >
            {open ? "▼" : "▶"} {title}
          </ButtonItem>
        </PanelSectionRow>
      </PanelSection>
      {open && children}
    </>
  );
}
