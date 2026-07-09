import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

type OpenAIModelsResponse = {
  data?: Array<{
    id: string;
    name?: string;
    context_window?: number;
    max_tokens?: number;
  }>;
};

type OllamaShowResponse = {
  details?: { family?: string };
  model_info?: Record<string, number>;
};

type RegisteredModel = {
  id: string;
  name: string;
  reasoning: boolean;
  input: Array<"text" | "image">;
  cost: { input: number; output: number; cacheRead: number; cacheWrite: number };
  contextWindow: number;
  maxTokens: number;
  compat?: {
    supportsDeveloperRole?: boolean;
    maxTokensField?: "max_completion_tokens" | "max_tokens";
  };
};

const DEFAULT_BASE_URL = "https://ollama.com/v1";
const DEFAULT_CONTEXT_WINDOW = 131072;
const DEFAULT_MAX_TOKENS = 8192;
const SHOW_CONCURRENCY = 8;
const FETCH_TIMEOUT_MS = 5000;

const normalizeBaseUrl = (url: string): string => url.replace(/\/+$/, "");

const nativeBaseFrom = (baseUrl: string): string =>
  baseUrl.endsWith("/v1") ? baseUrl.slice(0, -3) : baseUrl;

const fetchJson = async <T>(url: string, init: RequestInit = {}): Promise<T> => {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  try {
    const response = await fetch(url, { ...init, signal: controller.signal });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status} ${response.statusText} for ${url}`);
    }
    return (await response.json()) as T;
  } finally {
    clearTimeout(timer);
  }
};

const parseFallbackModels = (): RegisteredModel[] => {
  const raw = process.env.OLLAMA_CLOUD_MODELS ?? "";
  return raw
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean)
    .map((id) => ({
      id,
      name: id,
      reasoning: false,
      input: ["text"] as Array<"text" | "image">,
      cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
      contextWindow: DEFAULT_CONTEXT_WINDOW,
      maxTokens: DEFAULT_MAX_TOKENS,
    }));
};

const fetchContextLength = async (
  nativeBase: string,
  modelId: string,
  apiKey: string | undefined,
): Promise<number | undefined> => {
  try {
    const payload = await fetchJson<OllamaShowResponse>(`${nativeBase}/api/show`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(apiKey ? { Authorization: `Bearer ${apiKey}` } : {}),
      },
      body: JSON.stringify({ name: modelId }),
    });
    const arch = payload.details?.family ?? "";
    const value = payload.model_info?.[`${arch}.context_length`];
    return typeof value === "number" && value > 0 ? value : undefined;
  } catch {
    return undefined;
  }
};

const mapWithConcurrency = async <T, R>(
  items: T[],
  limit: number,
  worker: (item: T, index: number) => Promise<R>,
): Promise<R[]> => {
  const results: R[] = new Array(items.length);
  let cursor = 0;
  const runners = Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (true) {
      const index = cursor++;
      if (index >= items.length) return;
      results[index] = await worker(items[index]!, index);
    }
  });
  await Promise.all(runners);
  return results;
};

export default async function (pi: ExtensionAPI) {
  const baseUrl = normalizeBaseUrl(process.env.OLLAMA_CLOUD_BASE_URL ?? DEFAULT_BASE_URL);
  const apiKey = process.env.OLLAMA_CLOUD_API_KEY;
  const nativeBase = nativeBaseFrom(baseUrl);

  let models: RegisteredModel[] = [];

  // Without a key the Ollama API returns 401 (or hangs) — skip the network
  // call entirely and fall through to the fallback list so `pi --list-models`
  // stays responsive. The provider is still registered with whatever fallback
  // ids are configured, so users on shared/public machines can opt in via
  // OLLAMA_CLOUD_MODELS without needing a real key.
  if (!apiKey) {
    models = parseFallbackModels();
  } else {
    try {
      const payload = await fetchJson<OpenAIModelsResponse>(`${baseUrl}/models`, {
        headers: { Authorization: `Bearer ${apiKey}` },
      });
      const discovered = payload.data ?? [];

      // Probe /api/show for the real context window of each model. Ollama's
      // OpenAI-compat /v1/models omits context_window, so without this step
      // every model would silently fall back to the 131k default — a real
      // problem for models that ship with 256k / 512k / 1M context.
      const contextLengths = await mapWithConcurrency(discovered, SHOW_CONCURRENCY, (model) =>
        fetchContextLength(nativeBase, model.id, apiKey),
      );

      models = discovered.map((model, index) => ({
        id: model.id,
        name: model.name ?? model.id,
        reasoning: false,
        input: ["text"],
        cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
        contextWindow:
          model.context_window ?? contextLengths[index] ?? DEFAULT_CONTEXT_WINDOW,
        maxTokens: model.max_tokens ?? DEFAULT_MAX_TOKENS,
        compat: {
          supportsDeveloperRole: false,
          maxTokensField: "max_tokens",
        },
      }));
    } catch {
      models = parseFallbackModels();
    }
  }

  pi.registerProvider("ollama-cloud", {
    name: "Ollama Cloud",
    baseUrl,
    apiKey: "$OLLAMA_CLOUD_API_KEY",
    api: "openai-completions",
    authHeader: true,
    headers: {
      "Content-Type": "application/json",
    },
    models,
  });
}
