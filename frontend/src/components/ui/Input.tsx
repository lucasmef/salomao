import { forwardRef, type InputHTMLAttributes } from "react";
import styles from "./Field.module.css";

type Props = InputHTMLAttributes<HTMLInputElement> & {
  hasError?: boolean;
};

export const Input = forwardRef<HTMLInputElement, Props>(function Input(
  { hasError, className = "", ...rest },
  ref,
) {
  const cls = [styles.input, hasError ? styles.hasError : "", className].filter(Boolean).join(" ");
  return <input ref={ref} className={cls} {...rest} />;
});
