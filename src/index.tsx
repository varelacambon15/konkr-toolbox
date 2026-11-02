import { definePlugin } from "@decky/api";
import { staticClasses } from "@decky/ui";
import { FaToolbox } from "react-icons/fa";
import { Collapsible } from "./Collapsible";
import { TweaksSection } from "./TweaksSection";
import { DepsSection } from "./DepsSection";
import { MapsSection } from "./MapsSection";
import { SshSection } from "./SshSection";
import { RemoteSection } from "./RemoteSection";
import { ModsSection } from "./ModsSection";
import { t } from "./i18n";

// Cada herramienta es una sección cerrada detrás de un botón.
// Para añadir otra: crea su componente y ponlo aquí dentro de un <Collapsible>.
function Content() {
  return (
    <>
      <Collapsible id="tweaks" title={t.ktTitle}>
        <TweaksSection />
      </Collapsible>
      <Collapsible id="deps" title={t.depsTitle}>
        <DepsSection />
      </Collapsible>
      <Collapsible id="maps" title={t.mapsTitle}>
        <MapsSection />
      </Collapsible>
      <Collapsible id="mods" title={t.modsTitle}>
        <ModsSection />
      </Collapsible>
      <Collapsible id="ssh" title={t.sshTitle}>
        <SshSection />
      </Collapsible>
      <Collapsible id="remote" title={t.remoteTitle}>
        <RemoteSection />
      </Collapsible>
    </>
  );
}

export default definePlugin(() => ({
  name: "Konkr Toolbox",
  titleView: <div className={staticClasses.Title}>Konkr Toolbox</div>,
  content: <Content />,
  icon: <FaToolbox />,
}));
