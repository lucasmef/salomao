import { useId, type ReactNode } from "react";
import styles from "./Field.module.css";

type Props = {
  label?: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
  required?: boolean;
  htmlFor?: string;
  children: (id: string) => ReactNode;
};

export function Field({ label, hint, error, required, htmlFor, children }: Props) {
  const autoId = useId();
  const id = htmlFor ?? autoId;
  return (
    <div className={styles.field}>
      {label && (
        <label htmlFor={id} className={[styles.label, required ? styles.required : ""].filter(Boolean).join(" ")}>
          {label}
        </label>
      )}
      {children(id)}
      {error ? <span className={styles.error}>{error}</span> : hint ? <span className={styles.hint}>{hint}</span> : null}
    </div>
  );
}
