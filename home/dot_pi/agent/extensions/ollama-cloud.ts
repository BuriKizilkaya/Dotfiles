import { readFile } from "node:fs/promises";
import { homedir } from "node:os";
import { join } from "node:path";
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

type AuthEntry =
  | { type: "api_key"; key: string; env?: Record<string, string> }
  | { type: "oauth"; access: string; refresh?: string; expires?: number }
  | Record<string, unknown>;

const PROVIDER_ID = "ollama-cloud";
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

const resolveEnvValue = (raw: string): string | undefined => {
  if (!raw.startsWith("$")) return raw;
  const name = raw.startsWith("${") && raw.endsWith("}")
    ? raw.slice(2, -1)
    : raw.slice(1);
  return process.env[name];
};

// Resolve the API key the same way pi's runtime auth chain does: env var
// first, then auth.json (where /login stores it). The extension needs the
// key during startup to fetch the live model list, before pi has wired up
// its own resolution. If we find a key in auth.json, also export it as
// OLLAMA_CLOUD_API_KEY so the literal "$OLLAMA_CLOUD_API_KEY" reference
// passed to registerProvider resolves to a real value at request time.
const resolveApiKey = async (): Promise<string | undefined> => {
  const fromEnv = process.env.OLLAMA_CLOUD_API_KEY?.trim();
  if (fromEnv) return fromEnv;

  const authPath = join(homedir(), ".pi", "agent", "auth.json");
  try {
    const raw = await readFile(authPath, "utf8");
    const parsed = JSON.parse(raw) as Record<string, AuthEntry>;
    const entry = parsed[PROVIDER_ID];
    if (!entry) return undefined;
    let resolved: string | undefined;
    if ((entry as { type?: string }).type === "api_key") {
      const key = (entry as { key?: string }).key;
      if (!key) return undefined;
      resolved = resolveEnvValue(key);
    } else if ((entry as { type?: string }).type === "oauth") {
      resolved = (entry as { access?: string }).access;
    }
    if (resolved) {
      process.env.OLLAMA_CLOUD_API_KEY = resolved;
    }
    return resolved;
  } catch {
    return undefined;
  }
  return undefined;
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

export default async function (pi: ExtensionAPI) {
  const baseUrl = normalizeBaseUrl(process.env.OLLAMA_CLOUD_BASE_URL ?? DEFAULT_BASE_URL);
  const apiKey = await resolveApiKey();
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

  // Pass the apiKey as a "$ENV_VAR" reference so pi resolves it at request
  // time using its normal auth chain. resolveApiKey() above has already
  // mirrored the auth.json entry into process.env.OLLAMA_CLOUD_API_KEY,
  // so /login (which writes to auth.json) makes models selectable.
  pi.registerProvider(PROVIDER_ID, {
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
