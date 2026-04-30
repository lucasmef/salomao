import type { ReactNode } from "react";
import styles from "./States.module.css";

type Props = {
  title: string;
  message?: ReactNode;
  icon?: ReactNode;
  actions?: ReactNode;
};

export function EmptyState({ title, message, icon, actions }: Props) {
  return (
    <div className={styles.state} role="status">
      {icon ? <div className={styles.icon}>{icon}</div> : null}
      <h3 className={styles.title}>{title}</h3>
      {message && <p className={styles.message}>{message}</p>}
      {actions && <div className={styles.actions}>{actions}</div>}
    </div>
  );
}
