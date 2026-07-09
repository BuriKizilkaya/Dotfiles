#!/usr/bin/env python3
"""Blackbox test for the ollama-cloud pi extension.

Runs ``pi --list-models`` in a subprocess (so pi actually loads the extension)
and asserts that the context window pi advertises for each ollama-cloud model
matches the value the ollama API itself reports via ``POST /api/show``.

Pi's OpenAI-compat ``/v1/models`` does not expose context lengths, so the
ground truth is fetched from the native ``/api/show`` endpoint which returns
``model_info[<arch>.context_length]`` for every model.

Exits 0 when all assertions pass, 1 otherwise. The Ollama API key is read
from ``OLLAMA_CLOUD_API_KEY`` and forwarded to the child ``pi`` process.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from helpers.pi import run_cli  # noqa: E402
from helpers.runner import Runner  # noqa: E402


def _parse_size(token: str) -> int:
    """Parse a size token like ``131K``, ``1M``, ``8192`` to an int."""
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([KMkm]?)", token.strip())
    if not m:
        raise ValueError(f"unparseable size token: {token!r}")
    value = float(m.group(1))
    suffix = m.group(2).upper()
    if suffix == "K":
        return int(value * 1_000)
    if suffix == "M":
        return int(value * 1_000_000)
    return int(value)


def _parse_list_models(output: str) -> list[dict]:
    """Parse the ``pi --list-models`` table into a list of dicts.

    Columns: provider, model, context, max-out, thinking, images.
    """
    rows: list[dict] = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 6:
            continue
        provider, model, context, max_out, thinking, images = parts[:6]
        # Skip the header row.
        if provider == "provider" and model == "model":
            continue
        try:
            context_n = _parse_size(context)
            max_out_n = _parse_size(max_out)
        except ValueError:
            continue
        rows.append(
            {
                "provider": provider,
                "model": model,
                "contextWindow": context_n,
                "maxTokens": max_out_n,
                "thinking": thinking,
                "images": images,
            }
        )
    return rows


def _request_json(
    url: str,
    *,
    data: bytes | None = None,
    method: str = "GET",
    api_key: str | None = None,
    max_attempts: int = 3,
) -> dict:
    """Fetch a JSON payload with a short retry loop for transient errors."""
    import json
    import time
    import urllib.error
    import urllib.request

    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        req = urllib.request.Request(url, data=data, method=method)
        if api_key:
            req.add_header("Authorization", f"Bearer {api_key}")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # 4xx is not retriable (auth/quota/etc.).
            if 400 <= exc.code < 500:
                raise
            last_exc = exc
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            last_exc = exc
        if attempt < max_attempts:
            time.sleep(0.5 * attempt)
    raise RuntimeError(f"failed to fetch {url} after {max_attempts} attempts: {last_exc}")


def _fetch_api_models(
    base_url: str, api_key: str | None
) -> dict[str, dict[str, int]]:
    """Fetch ground-truth context/max-out from the Ollama Cloud API.

    Ollama's OpenAI-compat ``/v1/models`` endpoint does not expose
    ``context_window`` or ``max_tokens``, so we use the native
    ``POST /api/show`` endpoint to read ``model_info[<arch>.context_length]``
    for each model listed by ``/v1/models``.

    Returns a dict keyed by raw model id with ``contextWindow`` and
    ``maxTokens`` populated from the API (whichever fields are available).
    """
    openai_base = base_url.rstrip("/")
    native_base = openai_base[:-3] if openai_base.endswith("/v1") else openai_base

    # 1. Get the full model list from the OpenAI-compat endpoint.
    data = _request_json(f"{openai_base}/models", api_key=api_key)
    result: dict[str, dict[str, int]] = {}
    for entry in data.get("data", []):
        mid = entry.get("id")
        if not mid:
            continue
        result[mid] = {"contextWindow": 0, "maxTokens": 0}

    # 2. For each model, call /api/show to read model_info.<arch>.context_length.
    import json

    for mid in list(result.keys()):
        try:
            payload = _request_json(
                f"{native_base}/api/show",
                data=json.dumps({"name": mid}).encode("utf-8"),
                method="POST",
                api_key=api_key,
            )
        except RuntimeError:
            # Per-model show failures should not abort the whole run; a
            # missing context length just means we skip that comparison.
            continue
        model_info = payload.get("model_info") or {}
        arch = (payload.get("details") or {}).get("family") or ""
        ctx = model_info.get(f"{arch}.context_length")
        if ctx is not None:
            result[mid]["contextWindow"] = int(ctx)
        # Ollama does not publish max-output tokens in /api/show; leave as 0
        # and the caller will skip maxTokens assertions for that field.
    return result


# Pi renders context/max-out with one decimal of rounding (e.g. 131072 → 131.1K,
# 8192 → 8.2K, 1048576 → 1.0M). The M suffix uses a decimal divisor but only
# kicks in once a value crosses 1_000_000, which makes 1.0M ambiguous between
# 1_000_000 and 1_048_576. The comparison uses 5% tolerance to absorb both the
# sub-percent rounding and the binary-threshold ambiguity.
SIZE_TOLERANCE = 0.05


def main() -> int:
    r = Runner()
    r.section("Pi ollama-cloud extension — blackbox context check")

    if not os.environ.get("OLLAMA_CLOUD_API_KEY"):
        r.skip("OLLAMA_CLOUD_API_KEY not set — skipping blackbox run")
        return r.summary()
    try:
        rc, stdout, stderr = run_cli(["--list-models"], timeout=60)
    except FileNotFoundError:
        r._fail("pi binary not on PATH — cannot run blackbox check")
        return r.summary()
    except subprocess.TimeoutExpired:
        r._fail("pi --list-models timed out")
        return r.summary()

    if rc != 0:
        r._fail(f"pi --list-models exited {rc}: {stderr.strip()}")
        return r.summary()
    r._pass("pi --list-models exited 0")

    rows = _parse_list_models(stdout)
    r._pass(f"parsed {len(rows)} model row(s) from pi output")

    cloud_rows = [row for row in rows if row["provider"] == "ollama-cloud"]
    if not cloud_rows:
        r._fail("no ollama-cloud models registered — extension did not run")
        return r.summary()
    r._pass(f"ollama-cloud provider registered {len(cloud_rows)} model(s)")

    # Fetch ground-truth context windows from the ollama API directly.
    base_url = (
        os.environ.get("OLLAMA_CLOUD_BASE_URL", "https://ollama.com/v1").rstrip("/")
    )
    try:
        api_models = _fetch_api_models(base_url, os.environ.get("OLLAMA_CLOUD_API_KEY"))
    except RuntimeError as exc:
        r._fail(f"could not fetch API ground truth: {exc}")
        return r.summary()
    r._pass(
        f"fetched ground truth for {len(api_models)} model(s) via {base_url}/api/show"
    )

    for row in cloud_rows:
        api = api_models.get(row["model"])
        if api is None:
            r._fail(
                f"{row['model']!r} registered by pi but not present in API list"
            )
            continue
        want = api.get("contextWindow", 0)
        got = row["contextWindow"]
        if not want:
            r.skip(
                f"{row['model']!r}.contextWindow — API did not advertise a value (pi={got})"
            )
            continue
        lower = int(want * (1 - SIZE_TOLERANCE))
        upper = int(want * (1 + SIZE_TOLERANCE))
        if lower <= got <= upper:
            r._pass(
                f"{row['model']!r}.contextWindow matches API (api={want}, pi={got})"
            )
        else:
            r._fail(
                f"{row['model']!r}.contextWindow mismatch — API={want}, pi={got} "
                f"(tolerance ±{SIZE_TOLERANCE:.0%})"
            )

    return r.summary()


if __name__ == "__main__":
    sys.exit(main())
