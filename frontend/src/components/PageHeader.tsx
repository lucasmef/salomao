import type { ReactNode } from "react";
import "./PageHeader.css";

type Props = {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
};

export function PageHeader({ eyebrow, title, description, actions }: Props) {
  return (
    <header className="premium-page-header">
      <div className="header-main-content">
        <div className="header-copy">
          {eyebrow && <span className="header-eyebrow">{eyebrow}</span>}
          <h1 className="header-title">{title}</h1>
          {description && <p className="header-description">{description}</p>}
        </div>
        {actions && <div className="header-actions">{actions}</div>}
      </div>
    </header>
  );
}
