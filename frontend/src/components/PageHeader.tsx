import type { ReactNode } from "react";
import "./PageHeader.css";

type Props = {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
};

export function PageHeader({ actions }: Props) {
  if (!actions) {
    return null;
  }

  return (
    <header className="premium-page-header compact premium-page-header--actions-only">
      <div className="header-main-content">
        <div className="header-actions">{actions}</div>
      </div>
    </header>
  );
}
