import type { InputHTMLAttributes } from "react";

import { formatPtBrMoneyInput, sanitizePtBrMoneyInput } from "../lib/money";

type Props = Omit<InputHTMLAttributes<HTMLInputElement>, "type" | "value" | "onChange"> & {
  value: string;
  onValueChange: (value: string) => void;
  allowNegative?: boolean;
};

export function MoneyInput({ value, onValueChange, allowNegative = false, ...props }: Props) {
  return (
    <input
      {...props}
      type="text"
      inputMode="decimal"
      value={value}
      onBlur={() => onValueChange(formatPtBrMoneyInput(value))}
      onChange={(event) => onValueChange(sanitizePtBrMoneyInput(event.target.value, allowNegative))}
    />
  );
}
