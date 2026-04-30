import type { HTMLAttributes } from "react";
import styles from "./Card.module.css";

type Tone = "default" | "alt" | "flat";
type Density = "default" | "dense";

type Props = HTMLAttributes<HTMLDivElement> & {
  tone?: Tone;
  density?: Density;
};

export function Card({ tone = "default", density = "default", className = "", children, ...rest }: Props) {
  const cls = [
    styles.card,
    tone === "alt" ? styles.alt : "",
    tone === "flat" ? styles.flat : "",
    density === "dense" ? styles.dense : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <div className={cls} {...rest}>
      {children}
    </div>
  );
}
