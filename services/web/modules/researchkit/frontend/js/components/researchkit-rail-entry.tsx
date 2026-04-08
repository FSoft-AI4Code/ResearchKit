import ResearchKitPanel from "./researchkit-panel";
import ResearchKitRailIcon from "./researchkit-rail-icon";

const researchkitRailEntry = {
  key: "researchkit" as const,
  icon: ResearchKitRailIcon,
  title: "ResearchKit",
  component: <ResearchKitPanel />,
};

export default researchkitRailEntry;
