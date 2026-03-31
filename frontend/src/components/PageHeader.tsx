import type { ReactNode } from "react";

type Props = {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
};

export function PageHeader({ eyebrow, title, description, actions }: Props) {
  return (
    <section className="page-header">
      <div className="page-header-copy">
        {eyebrow && <p className="section-label">{eyebrow}</p>}
        <h2>{title}</h2>
        {description ? <p className="page-description">{description}</p> : null}
      </div>
      {actions ? <div className="page-header-actions">{actions}</div> : null}
    </section>
  );
}
