import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import styles from "./Button.module.css";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  iconLeft?: ReactNode;
  iconRight?: ReactNode;
};

export const Button = forwardRef<HTMLButtonElement, Props>(function Button(
  {
    variant = "primary",
    size = "sm",
    loading = false,
    iconLeft,
    iconRight,
    disabled,
    className = "",
    children,
    ...rest
  },
  ref,
) {
  const cls = [styles.button, styles[size], styles[variant], className].filter(Boolean).join(" ");
  return (
    <button ref={ref} className={cls} disabled={disabled || loading} {...rest}>
      {loading ? (
        <span className={styles.spinner} aria-hidden="true" />
      ) : iconLeft ? (
        <span className={styles.iconSlot}>{iconLeft}</span>
      ) : null}
      {children}
      {iconRight && !loading ? <span className={styles.iconSlot}>{iconRight}</span> : null}
    </button>
  );
});
