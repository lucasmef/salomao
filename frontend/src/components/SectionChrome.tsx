import type { ReactNode } from "react";
import { SectionTabs } from "./SectionTabs";
import type { MainNavChild } from "../data/navigation";
import "./SectionChrome.css";

type Props = {
  sectionLabel: string;
  tabLabel: string;
  title: string;
  description: string;
  tabs: MainNavChild[];
  children: ReactNode;
};

import { PageHeader } from "./PageHeader";

export function SectionChrome({
  tabs,
  children,
  title,
  description,
  sectionLabel,
}: Props) {
  return (
    <div className="section-container">
      <PageHeader
        eyebrow={sectionLabel}
        title={title}
        description={description}
      />

      {tabs.length > 1 ? <SectionTabs items={tabs} /> : null}

      <div className="section-content-card">
        {children}
      </div>
    </div>
  );
}
