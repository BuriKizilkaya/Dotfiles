/**
 * Ollama Cloud Provider for pi
 *
 * Uses pi's built-in openai-completions streaming.
 * Dynamically fetches correct contextWindow from Ollama model metadata.
 * Uses the full advertised context length by default.
 * Set OLLAMA_CONTEXT_WINDOW to override when a model advertises more than the host allows.
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

interface OllamaTag {
  name: string;
}

interface OllamaShowResponse {
  model_info?: Record<string, unknown>;
}

const DEFAULT_CONTEXT_WINDOW = 131_072;
const DEFAULT_MAX_TOKENS = 4096;

/** If set, hard-caps contextWindow to this value regardless of what api/show returns. */
const OVERRIDE_CONTEXT_WINDOW = process.env.OLLAMA_CONTEXT_WINDOW
  ? parseInt(process.env.OLLAMA_CONTEXT_WINDOW, 10)
  : null;

/** Extract context_length from model_info, accounting for varying architecture keys. */
function extractContextLength(showResponse: OllamaShowResponse): number {
  const info = showResponse.model_info;
  if (!info) {
    return OVERRIDE_CONTEXT_WINDOW ?? DEFAULT_CONTEXT_WINDOW;
  }

  let found: number | null = null;

  for (const [key, value] of Object.entries(info)) {
    if (key.endsWith(".context_length") && typeof value === "number") {
      found = value;
      break;
    }
  }

  // Use the model's advertised limit, but respect env override if smaller.
  let result = found ?? DEFAULT_CONTEXT_WINDOW;
  if (OVERRIDE_CONTEXT_WINDOW !== null) {
    result = Math.min(result, OVERRIDE_CONTEXT_WINDOW);
  }
  return result;
}

async function fetchModelMetadata(
  modelName: string,
  apiKey?: string,
): Promise<OllamaShowResponse | null> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (apiKey) headers["Authorization"] = `Bearer ${apiKey}`;

  try {
    const res = await fetch("https://ollama.com/api/show", {
      method: "POST",
      headers,
      body: JSON.stringify({ model: modelName, verbose: true }),
    });
    if (!res.ok) return null;
    return (await res.json()) as OllamaShowResponse;
  } catch {
    return null;
  }
}

async function discoverModels(apiKey?: string): Promise<OllamaTag[]> {
  const headers: Record<string, string> = {};
  if (apiKey) headers["Authorization"] = `Bearer ${apiKey}`;
  const res = await fetch("https://ollama.com/api/tags", { headers });
  if (!res.ok) return [];
  const data = (await res.json()) as { models?: OllamaTag[] };
  return data.models ?? [];
}

export default async function (pi: ExtensionAPI) {
  const apiKey = process.env.OLLAMA_CLOUD_API_KEY;
  let discovered: OllamaTag[] = [];

  try {
    discovered = await discoverModels(apiKey);
  } catch {
    // optional discovery
  }

  const models = await Promise.all(
    discovered.length > 0
      ? discovered.map(async (m) => {
          const metadata = await fetchModelMetadata(m.name, apiKey);
          const contextWindow = extractContextLength(metadata);

          return {
            id: m.name,
            name: m.name,
            reasoning: false,
            input: ["text"] as ("text" | "image")[],
            cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
            contextWindow,
            maxTokens: DEFAULT_MAX_TOKENS,
          };
        })
      : [
          Promise.resolve({
            id: "gpt-oss:120b",
            name: "GPT-OSS 120B (Ollama Cloud)",
            reasoning: false,
            input: ["text"] as ("text" | "image")[],
            cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
            contextWindow: OVERRIDE_CONTEXT_WINDOW ?? DEFAULT_CONTEXT_WINDOW,
            maxTokens: DEFAULT_MAX_TOKENS,
          }),
        ],
  );

  pi.registerProvider("ollama-cloud", {
    name: "Ollama Cloud",
    baseUrl: "https://ollama.com/v1",
    apiKey: "$OLLAMA_CLOUD_API_KEY",
    api: "openai-completions",
    authHeader: true,
    models,
  });
}