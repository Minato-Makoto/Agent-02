type RuntimeContextWindow = {
  contextWindow: number;
  source: "props";
  fetchedAt: number;
};

const LLAMA_RUNTIME_CACHE = new Map<string, RuntimeContextWindow>();
const LLAMA_RUNTIME_INFLIGHT = new Map<string, Promise<RuntimeContextWindow | undefined>>();

function normalizePositiveInt(value: unknown): number | undefined {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return undefined;
  }
  const normalized = Math.floor(value);
  return normalized > 0 ? normalized : undefined;
}

function isTestEnv(): boolean {
  return Boolean(process.env.VITEST || process.env.NODE_ENV === "test");
}

function isLocalHostname(hostname: string): boolean {
  const normalized = hostname.trim().toLowerCase();
  return normalized === "127.0.0.1" || normalized === "localhost" || normalized === "::1";
}

function normalizeLlamaBaseUrl(baseUrl?: string): string | undefined {
  const trimmed = baseUrl?.trim();
  if (!trimmed) {
    return undefined;
  }
  try {
    const url = new URL(trimmed);
    if (!isLocalHostname(url.hostname)) {
      return undefined;
    }
    if (!/\/v1\/?$/.test(url.pathname)) {
      return undefined;
    }
    url.pathname = url.pathname.replace(/\/v1\/?$/, "");
    return url.toString().replace(/\/+$/, "");
  } catch {
    return undefined;
  }
}

function buildCacheKey(baseUrl: string, modelId: string): string {
  return `${baseUrl}::${modelId}`;
}

async function fetchRuntimeProps(params: {
  baseUrl: string;
  modelId: string;
  headers?: Record<string, string>;
  autoload?: boolean;
}): Promise<RuntimeContextWindow | undefined> {
  const url = new URL(`${params.baseUrl}/props`);
  url.searchParams.set("model", params.modelId);
  if (params.autoload === false) {
    url.searchParams.set("autoload", "false");
  }
  const response = await fetch(url, {
    headers: params.headers,
    signal: AbortSignal.timeout(5_000),
  });
  if (!response.ok) {
    return undefined;
  }
  const payload = (await response.json()) as {
    default_generation_settings?: { n_ctx?: number };
  };
  const contextWindow = normalizePositiveInt(payload?.default_generation_settings?.n_ctx);
  if (!contextWindow) {
    return undefined;
  }
  return {
    contextWindow,
    source: "props",
    fetchedAt: Date.now(),
  };
}

export function lookupCachedLlamaRuntimeContextWindow(params: {
  baseUrl?: string;
  modelId?: string;
}): number | undefined {
  const normalizedBaseUrl = normalizeLlamaBaseUrl(params.baseUrl);
  const modelId = params.modelId?.trim();
  if (!normalizedBaseUrl || !modelId) {
    return undefined;
  }
  return LLAMA_RUNTIME_CACHE.get(buildCacheKey(normalizedBaseUrl, modelId))?.contextWindow;
}

export function isLocalLlamaRuntimeTarget(baseUrl?: string): boolean {
  return Boolean(normalizeLlamaBaseUrl(baseUrl));
}

export async function resolveLlamaRuntimeContextWindow(params: {
  baseUrl?: string;
  modelId?: string;
  headers?: Record<string, string>;
  allowAutoload?: boolean;
}): Promise<RuntimeContextWindow | undefined> {
  if (isTestEnv()) {
    const cached = lookupCachedLlamaRuntimeContextWindow(params);
    return cached ? { contextWindow: cached, source: "props", fetchedAt: Date.now() } : undefined;
  }

  const normalizedBaseUrl = normalizeLlamaBaseUrl(params.baseUrl);
  const modelId = params.modelId?.trim();
  if (!normalizedBaseUrl || !modelId) {
    return undefined;
  }

  const cacheKey = buildCacheKey(normalizedBaseUrl, modelId);
  const cached = LLAMA_RUNTIME_CACHE.get(cacheKey);
  if (cached) {
    return cached;
  }

  const existing = LLAMA_RUNTIME_INFLIGHT.get(cacheKey);
  if (existing) {
    return existing;
  }

  const task = (async () => {
    const loadedOnly = await fetchRuntimeProps({
      baseUrl: normalizedBaseUrl,
      modelId,
      headers: params.headers,
      autoload: false,
    });
    if (loadedOnly) {
      LLAMA_RUNTIME_CACHE.set(cacheKey, loadedOnly);
      return loadedOnly;
    }
    if (params.allowAutoload === false) {
      return undefined;
    }
    const autoloaded = await fetchRuntimeProps({
      baseUrl: normalizedBaseUrl,
      modelId,
      headers: params.headers,
      autoload: true,
    });
    if (autoloaded) {
      LLAMA_RUNTIME_CACHE.set(cacheKey, autoloaded);
    }
    return autoloaded;
  })().finally(() => {
    LLAMA_RUNTIME_INFLIGHT.delete(cacheKey);
  });

  LLAMA_RUNTIME_INFLIGHT.set(cacheKey, task);
  return task;
}

export function clearLlamaRuntimeContextCacheForTest() {
  LLAMA_RUNTIME_CACHE.clear();
  LLAMA_RUNTIME_INFLIGHT.clear();
}
