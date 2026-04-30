import { forwardRef, type SelectHTMLAttributes } from "react";
import styles from "./Field.module.css";

type Props = SelectHTMLAttributes<HTMLSelectElement> & {
  hasError?: boolean;
};

export const Select = forwardRef<HTMLSelectElement, Props>(function Select(
  { hasError, className = "", children, ...rest },
  ref,
) {
  const cls = [styles.select, hasError ? styles.hasError : "", className].filter(Boolean).join(" ");
  return (
    <select ref={ref} className={cls} {...rest}>
      {children}
    </select>
  );
});
