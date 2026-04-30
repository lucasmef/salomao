import type { ReactNode } from "react";
import styles from "./StatusPill.module.css";

type Status = "online" | "idle" | "offline";

type Props = {
  status?: Status;
  pulse?: boolean;
  children?: ReactNode;
};

const dotClass: Record<Status, string> = {
  online: styles.dotOnline,
  idle: styles.dotIdle,
  offline: styles.dotOffline,
};

export function StatusPill({ status = "online", pulse = false, children }: Props) {
  return (
    <span className={styles.pill}>
      <span
        className={[styles.dot, dotClass[status], pulse ? styles.dotPulse : ""].filter(Boolean).join(" ")}
        aria-hidden="true"
      />
      {children}
    </span>
  );
}
