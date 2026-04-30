import type { ReactNode } from "react";
import styles from "./States.module.css";

type Props = {
  title?: string;
  message?: ReactNode;
  actions?: ReactNode;
};

export function ErrorState({
  title = "Algo deu errado",
  message = "Não foi possível carregar este conteúdo. Tente novamente em instantes.",
  actions,
}: Props) {
  return (
    <div className={styles.state} role="alert">
      <div className={[styles.icon, styles.iconError].join(" ")}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10" />
          <line x1="12" y1="8" x2="12" y2="12" />
          <line x1="12" y1="16" x2="12.01" y2="16" />
        </svg>
      </div>
      <h3 className={styles.title}>{title}</h3>
      {message && <p className={styles.message}>{message}</p>}
      {actions && <div className={styles.actions}>{actions}</div>}
    </div>
  );
}
