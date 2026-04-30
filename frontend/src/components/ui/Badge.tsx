import type { ReactNode } from "react";
import styles from "./Badge.module.css";

type Tone = "neutral" | "urgent" | "success" | "info" | "warn";

type Props = {
  tone?: Tone;
  children: ReactNode;
};

export function Badge({ tone = "neutral", children }: Props) {
  return <span className={[styles.badge, styles[tone]].join(" ")}>{children}</span>;
}
