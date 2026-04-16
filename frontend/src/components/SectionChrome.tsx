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

export function SectionChrome({
  tabs,
  children,
  title,
  description,
}: Props) {
  return (
    <div className="section-container">
      <header className="section-header">
        <h1 className="section-title">{title}</h1>
        {description && <p className="section-description">{description}</p>}
      </header>

      {tabs.length > 1 ? <SectionTabs items={tabs} /> : null}

      <div className="section-content-card">
        {children}
      </div>
    </div>
  );
}
