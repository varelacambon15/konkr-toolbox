import { definePlugin } from "@decky/api";
import { staticClasses } from "@decky/ui";
import { FaToolbox } from "react-icons/fa";
import { TweaksSection } from "./TweaksSection";
import { SshSection } from "./SshSection";

// Cada herramienta es una sección. Para añadir otra: crea su componente y ponlo aquí.
function Content() {
  return (
    <>
      <TweaksSection />
      <SshSection />
    </>
  );
}

export default definePlugin(() => ({
  name: "Konkr Toolbox",
  titleView: <div className={staticClasses.Title}>Konkr Toolbox</div>,
  content: <Content />,
  icon: <FaToolbox />,
}));
