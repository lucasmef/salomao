const API_BASE = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000/api/v1";
let resolvedApiBase: string | null = null;
let resolvingApiBase: Promise<string> | null = null;
let networkActivityCount = 0;
const networkActivityListeners = new Set<() => void>();
const inflightJsonRequests = new Map<string, Promise<unknown>>();

type RequestOptions = RequestInit & {
  token?: string | null;
};

function notifyNetworkActivityListeners() {
  networkActivityListeners.forEach((listener) => listener());
}

function beginNetworkActivity() {
  networkActivityCount += 1;
  notifyNetworkActivityListeners();

  return () => {
    networkActivityCount = Math.max(0, networkActivityCount - 1);
    notifyNetworkActivityListeners();
  };
}

export function getNetworkActivityCount() {
  return networkActivityCount;
}

export function subscribeToNetworkActivity(listener: () => void) {
  networkActivityListeners.add(listener);
  return () => {
    networkActivityListeners.delete(listener);
  };
}

function normalizeApiRoot(base: string) {
  return base.replace(/\/+$/, "");
}

function buildJsonRequestKey(path: string, init?: RequestOptions) {
  const method = (init?.method ?? "GET").toUpperCase();
  if (method !== "GET") {
    return null;
  }
  return JSON.stringify({
    method,
    path,
    token: init?.token ?? null,
  });
}

function isLocalHostname(hostname: string) {
  return hostname === "localhost" || hostname === "127.0.0.1";
}

function getApiBaseCandidates() {
  const configuredBase = normalizeApiRoot(API_BASE);
  const sameOriginCandidate = normalizeApiRoot(`${window.location.origin}/api/v1`);
  const candidates = isLocalHostname(window.location.hostname)
    ? [configuredBase]
    : [sameOriginCandidate, configuredBase];

  const portCandidates = [8000, 8001, 8002, 8003, 8010, 8011, 8012, 8013, 8014, 8015];
  const localCandidates = portCandidates.flatMap((port) => [
    `http://127.0.0.1:${port}/api/v1`,
    `http://localhost:${port}/api/v1`,
    `${window.location.protocol}//${window.location.hostname}:${port}/api/v1`,
  ]);

  for (const candidate of localCandidates.map(normalizeApiRoot)) {
    if (!candidates.includes(candidate)) {
      candidates.push(candidate);
    }
  }

  if (!candidates.includes(sameOriginCandidate)) {
    candidates.push(sameOriginCandidate);
  }

  return candidates;
}

async function resolveApiBase() {
  if (resolvedApiBase) {
    return resolvedApiBase;
  }

  if (!resolvingApiBase) {
    resolvingApiBase = (async () => {
      let fallbackCandidate: string | null = null;
      for (const candidate of getApiBaseCandidates()) {
        try {
          const response = await fetch(`${candidate}/meta/instance`);
          if (!response.ok) {
            continue;
          }
          const payload = (await response.json()) as {
            app?: string;
            purchase_planning_enabled?: boolean;
            features?: string[];
          };
          const isTargetApp = payload.app === "gestor-financeiro" && payload.purchase_planning_enabled;
          if (!isTargetApp) {
            continue;
          }
          if (!fallbackCandidate) {
            fallbackCandidate = candidate;
          }
          if (payload.features?.includes("boletos-import-inter-zip")) {
            resolvedApiBase = candidate;
            return candidate;
          }
        } catch {
          // Try next candidate.
        }
      }

      resolvedApiBase = fallbackCandidate ?? getApiBaseCandidates()[0];
      return resolvedApiBase;
    })();
  }

  return resolvingApiBase;
}

type ClientErrorPayload = {
  source: string;
  message: string;
  path?: string;
  method?: string;
  status_code?: number;
  request_url?: string;
  api_base?: string;
  details?: string;
  screen?: string;
  user_agent?: string;
};

async function reportClientError(payload: ClientErrorPayload) {
  if (payload.path?.startsWith("/meta/client-error")) {
    return;
  }

  const body = JSON.stringify({
    ...payload,
    screen: payload.screen ?? window.location.pathname,
    user_agent: payload.user_agent ?? window.navigator.userAgent,
  });

  for (const candidate of getApiBaseCandidates()) {
    try {
      await fetch(`${candidate}/meta/client-error`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body,
      });
      return;
    } catch {
      // Best-effort only.
    }
  }
}

export async function fetchJson<T>(path: string, init?: RequestOptions): Promise<T> {
  const requestKey = buildJsonRequestKey(path, init);
  if (requestKey) {
    const existingRequest = inflightJsonRequests.get(requestKey);
    if (existingRequest) {
      return existingRequest as Promise<T>;
    }
  }

  const requestPromise = (async () => {
    const finishNetworkActivity = beginNetworkActivity();
    const headers = new Headers(init?.headers ?? {});
    const isFormData = init?.body instanceof FormData;
    if (init?.token) {
      headers.set("X-Auth-Token", init.token);
    }
    if (!isFormData && init?.body && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }

    try {
      const preferredBase = await resolveApiBase();
      const candidates = [preferredBase, ...getApiBaseCandidates().filter((candidate) => candidate !== preferredBase)];
      let lastError: unknown = null;

      for (const candidate of candidates) {
        try {
          const candidateResponse = await fetch(`${candidate}${path}`, {
            ...init,
            headers,
            credentials: init?.credentials ?? "include",
          });
          if (!candidateResponse.ok) {
            const message = (await candidateResponse.text()) || "Falha na comunicacao com a API.";
            await reportClientError({
              source: "frontend.fetch",
              message,
              path,
              method: init?.method ?? "GET",
              status_code: candidateResponse.status,
              request_url: `${candidate}${path}`,
              api_base: candidate,
              details: message.slice(0, 2000),
            });
            throw new Error(message);
          }
          if (candidateResponse.status === 204) {
            return undefined as T;
          }
          return (await candidateResponse.json()) as T;
        } catch (error) {
          lastError = error;
          if (!(error instanceof TypeError)) {
            throw error;
          }
          await reportClientError({
            source: "frontend.fetch",
            message: "Falha de conexao com a API local",
            path,
            method: init?.method ?? "GET",
            request_url: `${candidate}${path}`,
            api_base: candidate,
            details: error.message,
          });
        }
      }

      if (lastError instanceof TypeError) {
        throw new Error(
          `Não foi possível conectar com a API local. Tente abrir o backend em http://127.0.0.1:8000/docs ou reiniciar pelo iniciar-sistema.bat.`,
        );
      }
      throw lastError;
    } finally {
      finishNetworkActivity();
    }
  })();

  if (requestKey) {
    inflightJsonRequests.set(requestKey, requestPromise);
  }

  try {
    return await requestPromise;
  } finally {
    if (requestKey) {
      inflightJsonRequests.delete(requestKey);
    }
  }
}

export async function downloadFile(
  path: string,
  options: {
    token?: string | null;
    filename: string;
    method?: string;
    body?: BodyInit | null;
    headers?: HeadersInit;
  },
) {
  const finishNetworkActivity = beginNetworkActivity();
  const { token, filename, method = "GET", body, headers: extraHeaders } = options;
  const headers = new Headers(extraHeaders ?? {});
  const isFormData = body instanceof FormData;
  if (token) {
    headers.set("X-Auth-Token", token);
  }
  if (!isFormData && body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  try {
    let lastError: unknown = null;

    const preferredBase = await resolveApiBase();
    for (const candidate of [preferredBase, ...getApiBaseCandidates().filter((item) => item !== preferredBase)]) {
      try {
        const candidateResponse = await fetch(`${candidate}${path}`, {
          method,
          body,
          headers,
          credentials: "include",
        });
        if (!candidateResponse.ok) {
          const message = (await candidateResponse.text()) || "Falha ao gerar arquivo.";
          await reportClientError({
            source: "frontend.download",
            message,
            path,
            method,
            status_code: candidateResponse.status,
            request_url: `${candidate}${path}`,
            api_base: candidate,
            details: message.slice(0, 2000),
          });
          throw new Error(message);
        }
        const blob = await candidateResponse.blob();
        const contentDisposition = candidateResponse.headers.get("Content-Disposition") ?? "";
        const matchedFilename = /filename=\"?([^\";]+)\"?/i.exec(contentDisposition)?.[1];
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = matchedFilename || filename;
        anchor.click();
        URL.revokeObjectURL(url);
        return;
      } catch (error) {
        lastError = error;
        if (!(error instanceof TypeError)) {
          throw error;
        }
        await reportClientError({
          source: "frontend.download",
          message: "Falha de conexão com a API local ao baixar arquivo",
          path,
          method,
          request_url: `${candidate}${path}`,
          api_base: candidate,
          details: error.message,
        });
      }
    }

    if (lastError instanceof TypeError) {
      throw new Error("Não foi possível conectar com a API local para gerar o arquivo.");
    }
    throw lastError;
  } finally {
    finishNetworkActivity();
  }
}
