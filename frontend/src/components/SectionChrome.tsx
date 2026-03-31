import type { ReactNode } from "react";

import { SectionTabs } from "./SectionTabs";
import type { MainNavChild } from "../data/navigation";

type Props = {
  sectionLabel: string;
  tabLabel: string;
  title: string;
  description: string;
  tabs: MainNavChild[];
  children: ReactNode;
};

export function SectionChrome({
  tabs,
  children,
}: Props) {
  return (
    <div className="section-page">
      {tabs.length > 1 ? <SectionTabs items={tabs} /> : null}

      <div className="section-page-body">{children}</div>
    </div>
  );
}
