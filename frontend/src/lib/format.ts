export function formatMoney(value: string | number | null | undefined) {
  const numeric = Number(value ?? 0);
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(Number.isFinite(numeric) ? numeric : 0);
}

export function formatMoneyNumber(value: string | number | null | undefined) {
  const numeric = Number(value ?? 0);
  return new Intl.NumberFormat("pt-BR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number.isFinite(numeric) ? numeric : 0);
}

export function formatDate(value: string | null | undefined) {
  if (!value) {
    return "Sem data";
  }
  const [year, month, day] = value.slice(0, 10).split("-");
  if (!year || !month || !day) {
    return value;
  }
  return `${day}/${month}/${year}`;
}

export function formatDateTime(value: string | null | undefined) {
  if (!value) {
    return "Sem data";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return formatDate(value);
  }

  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function formatBytes(value: number) {
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function extractApiErrorMessage(detail: unknown): string | null {
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => extractApiErrorMessage(item))
      .filter((item): item is string => Boolean(item));
    return messages.length ? messages.join(" | ") : null;
  }
  if (detail && typeof detail === "object") {
    const record = detail as Record<string, unknown>;
    if (typeof record.msg === "string") {
      const loc = Array.isArray(record.loc)
        ? record.loc
            .filter((item) => typeof item === "string" || typeof item === "number")
            .join(".")
        : "";
      return loc ? `${loc}: ${record.msg}` : record.msg;
    }
    if ("detail" in record) {
      return extractApiErrorMessage(record.detail);
    }
  }
  return null;
}

export function parseApiError(error: unknown) {
  if (error instanceof Error) {
    try {
      const parsed = JSON.parse(error.message) as { detail?: unknown };
      return extractApiErrorMessage(parsed.detail) ?? error.message;
    } catch {
      return error.message;
    }
  }
  return "Falha nao identificada.";
}

export function normalizeDisplayText(value: string | null | undefined) {
  if (!value) {
    return "";
  }

  const text = String(value);
  if (!/[ÃÂâ]/.test(text)) {
    return text;
  }

  try {
    const bytes = Uint8Array.from(text, (character) => character.charCodeAt(0) & 0xff);
    const decoded = new TextDecoder("utf-8", { fatal: false }).decode(bytes);
    if (/[�]/.test(decoded)) {
      return text;
    }
    return decoded;
  } catch {
    return text;
  }
}

export function formatEntryStatus(value: string | null | undefined) {
  const normalized = normalizeDisplayText(value).trim().toLowerCase();
  const labels: Record<string, string> = {
    open: "Em aberto",
    planned: "Em aberto",
    partial: "Em aberto",
    settled: "Pago",
    cancelled: "Cancelado",
    processed: "Processado",
    completed: "Concluido",
    pending: "Pendente",
    failed: "Falhou",
    error: "Erro",
    overdue: "Atrasado",
    paid: "Pago",
  };

  return labels[normalized] ?? normalizeDisplayText(value) ?? "-";
}

export function isGroupedEntryTitle(value: string | null | undefined) {
  const normalized = normalizeDisplayText(value).trim().toLowerCase();
  return normalized.startsWith("recebimento agrupado") || normalized.startsWith("pagamento agrupado");
}
