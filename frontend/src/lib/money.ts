export function sanitizePtBrMoneyInput(value: string, allowNegative = false) {
  const raw = String(value ?? "").replace(/[^\d,.\-]/g, "");
  const isNegative = allowNegative && raw.includes("-");
  const unsigned = raw.replace(/-/g, "");
  const firstCommaIndex = unsigned.indexOf(",");

  if (firstCommaIndex === -1) {
    return `${isNegative ? "-" : ""}${unsigned}`;
  }

  const integerPart = unsigned.slice(0, firstCommaIndex);
  const decimalPart = unsigned
    .slice(firstCommaIndex + 1)
    .replace(/,/g, "");

  return `${isNegative ? "-" : ""}${integerPart},${decimalPart}`;
}

function parseMoneyParts(value: string) {
  const sanitized = sanitizePtBrMoneyInput(String(value ?? ""), true);
  if (!sanitized || sanitized === "-" || sanitized === "," || sanitized === "-,") {
    return { isNegative: false, integerPart: "0", decimalDigits: "00" };
  }

  const isNegative = sanitized.startsWith("-");
  const unsigned = sanitized.replace(/-/g, "");
  const lastCommaIndex = unsigned.lastIndexOf(",");
  const lastDotIndex = unsigned.lastIndexOf(".");
  const lastSeparatorIndex = Math.max(lastCommaIndex, lastDotIndex);

  if (lastSeparatorIndex === -1) {
    return {
      isNegative,
      integerPart: unsigned.replace(/\D/g, "") || "0",
      decimalDigits: "00",
    };
  }

  const separator = unsigned[lastSeparatorIndex];
  const separatorMatches = unsigned.match(new RegExp(`\\${separator}`, "g")) ?? [];
  const digitsAfterSeparator = unsigned.slice(lastSeparatorIndex + 1).replace(/\D/g, "");
  const hasMixedSeparators = lastCommaIndex !== -1 && lastDotIndex !== -1;
  const usesDecimalSeparator =
    hasMixedSeparators || (separatorMatches.length === 1 && digitsAfterSeparator.length > 0 && digitsAfterSeparator.length <= 2);

  if (!usesDecimalSeparator) {
    return {
      isNegative,
      integerPart: unsigned.replace(/\D/g, "") || "0",
      decimalDigits: "00",
    };
  }

  return {
    isNegative,
    integerPart: unsigned.slice(0, lastSeparatorIndex).replace(/\D/g, "") || "0",
    decimalDigits: digitsAfterSeparator.slice(0, 2).padEnd(2, "0"),
  };
}

export function normalizePtBrMoneyInput(value: string | number | null | undefined) {
  if (typeof value === "number") {
    return value.toFixed(2);
  }

  const { isNegative, integerPart, decimalDigits } = parseMoneyParts(String(value ?? ""));
  const normalizedInteger = integerPart.replace(/^0+(?=\d)/, "");

  return `${isNegative ? "-" : ""}${normalizedInteger}.${decimalDigits}`;
}

export function formatPtBrMoneyInput(value: string | number | null | undefined) {
  const normalized = normalizePtBrMoneyInput(value);
  const isNegative = normalized.startsWith("-");
  const unsigned = normalized.replace(/-/g, "");
  const [integerPart, decimalPart = "00"] = unsigned.split(".", 2);
  const formattedInteger = integerPart.replace(/\B(?=(\d{3})+(?!\d))/g, ".");

  return `${isNegative ? "-" : ""}${formattedInteger},${decimalPart.padEnd(2, "0").slice(0, 2)}`;
}
