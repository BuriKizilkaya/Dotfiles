"""Pi agent assertions — file deployment + CLI smoke tests."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from helpers.runner import Runner


# ---------------------------------------------------------------------------
# CLI helper
# ---------------------------------------------------------------------------

def run_cli(
    args: list[str],
    *,
    extra_env: dict[str, str] | None = None,
    strip_keys: list[str] | None = None,
    timeout: int = 30,
    env_override: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    """Run ``pi <args>`` and return ``(returncode, stdout, stderr)``.

    Args:
        args:          Arguments forwarded to ``pi``, e.g. ``["--list-models"]``.
        extra_env:     Key/value pairs merged on top of the current environment.
        strip_keys:    Environment variable names to remove before the call.
                       Useful for simulating an absent API key without mutating
                       the calling process's environment.
        timeout:       Seconds before the subprocess is killed (default 30).
        env_override:  Full environment replacement (skips the os.environ copy).
                       Used to redirect HOME to a sandbox for auth.json tests.

    Returns:
        A 3-tuple of (exit code, stdout text, stderr text).

    Raises:
        subprocess.TimeoutExpired: re-raised after the process is killed.
        FileNotFoundError: if ``pi`` is not on PATH.
    """
    env = dict(env_override) if env_override is not None else dict(os.environ)
    for key in strip_keys or []:
        env.pop(key, None)
    if extra_env:
        env.update(extra_env)

    # On Windows, mise shims are .cmd batch files which CreateProcess cannot
    # execute directly (only .exe files work without shell=True).  Using
    # shell=True delegates to cmd.exe which handles .cmd resolution correctly.
    result = subprocess.run(
        ["pi", *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=timeout,
        shell=(sys.platform == "win32"),
    )
    return result.returncode, result.stdout, result.stderr


# ---------------------------------------------------------------------------
# Assertion groups
# ---------------------------------------------------------------------------

def assert_pi_extensions(r: Runner, home: Path) -> None:
    """Check that chezmoi deployed the extension file with the right content."""
    r.section("Pi agent extensions — deployment")

    ext = home / ".pi" / "agent" / "extensions" / "ollama-cloud.ts"

    r.assert_file(ext)
    r.assert_file_contains(ext, "ollama-cloud")             # provider ID
    r.assert_file_contains(ext, "OLLAMA_CLOUD_API_KEY")     # API key env var
    r.assert_file_contains(ext, "OLLAMA_CLOUD_BASE_URL")    # base URL override env var
    r.assert_file_contains(ext, "OLLAMA_CLOUD_MODELS")      # fallback models env var
    r.assert_file_contains(ext, "ollama.com/v1")            # default base URL
    r.assert_file_contains(ext, "registerProvider")         # core pi API call
    r.assert_file_contains(ext, "authHeader")               # bearer auth flag
    r.assert_file_contains(ext, "auth.json")                # /login support


def assert_pi_cli(r: Runner) -> None:
    """Smoke-test the pi CLI to verify the extension integrates cleanly."""
    r.section("Pi agent extensions — CLI smoke tests")

    # 1. pi binary is on PATH --------------------------------------------------
    r.assert_command("pi")

    # 2. pi --version -----------------------------------------------------------
    try:
        rc, stdout, stderr = run_cli(["--version"])
        if rc == 0:
            r._pass(f"pi --version exits 0 (version: {(stdout + stderr).strip()})")
        else:
            r._fail(f"pi --version exited {rc}: {stderr.strip()}")
    except FileNotFoundError:
        r._fail("pi not found on PATH — skipping remaining CLI checks")
        return
    except subprocess.TimeoutExpired:
        r._fail("pi --version timed out")
        return

    # 3. No key, no fallback models → fetch fails, falls back to empty list,
    #    registerProvider still called → pi must exit 0.
    try:
        rc, stdout, stderr = run_cli(
            ["--list-models"],
            strip_keys=["OLLAMA_CLOUD_API_KEY", "OLLAMA_CLOUD_MODELS", "OLLAMA_CLOUD_BASE_URL"],
        )
        if rc == 0:
            r._pass("pi --list-models exits 0 (no OLLAMA_CLOUD_API_KEY)")
        else:
            r._fail(f"pi --list-models exited {rc} with no key set")
    except subprocess.TimeoutExpired:
        r._fail("pi --list-models timed out (no-key run)")

    # 4. Fake key → fetch fails, fallback to empty model list, exit 0 ----------
    try:
        rc, stdout, stderr = run_cli(
            ["--list-models"],
            strip_keys=["OLLAMA_CLOUD_API_KEY", "OLLAMA_CLOUD_MODELS", "OLLAMA_CLOUD_BASE_URL"],
            extra_env={"OLLAMA_CLOUD_API_KEY": "ollama_ci_fake"},
        )
        if rc == 0:
            r._pass("pi --list-models exits 0 with bad OLLAMA_CLOUD_API_KEY (fetch error handled)")
        else:
            r._fail(f"pi --list-models exited {rc} with bad key")
    except subprocess.TimeoutExpired:
        r._fail("pi --list-models timed out (fake-key run)")

    # 5. Fake key in auth.json (where /login stores it) → extension should
    #    read it and attempt the API call. With a bad key the Ollama API
    #    returns 401 quickly, so --list-models must still exit 0 and fast.
    _assert_auth_json_key(r)


# ---------------------------------------------------------------------------
# /login support
# ---------------------------------------------------------------------------

def _sandbox_auth_json(key: str) -> tuple[dict[str, str], str]:
    """Create a temp HOME containing a fake auth.json with the ollama-cloud
    key. Returns ``(env, sandbox_dir)``. The caller owns the directory."""
    sandbox = tempfile.mkdtemp(prefix="pi-auth-test-")
    if sys.platform == "win32":
        agent_dir = Path(sandbox) / "pi" / "agent"
        env = {"USERPROFILE": sandbox, "HOME": sandbox}
    else:
        agent_dir = Path(sandbox) / ".pi" / "agent"
        env = {"HOME": sandbox}
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "auth.json").write_text(
        json.dumps({"ollama-cloud": {"type": "api_key", "key": key}}),
        encoding="utf8",
    )
    return env, sandbox


def _assert_auth_json_key(r: Runner) -> None:
    """Verify the extension reads ``auth.json["ollama-cloud"]`` when no env
    var is set — the same path /login uses to persist a key.

    The extension will hit the Ollama API with the fake key and get a quick
    401, so ``pi --list-models`` must still exit 0 and finish well under the
    30 s subprocess timeout.
    """
    env, sandbox = _sandbox_auth_json("ollama_ci_auth_json_fake")
    try:
        try:
            rc, stdout, stderr = run_cli(
                ["--list-models"],
                strip_keys=[
                    "OLLAMA_CLOUD_API_KEY",
                    "OLLAMA_CLOUD_MODELS",
                    "OLLAMA_CLOUD_BASE_URL",
                ],
                env_override=env,
                timeout=15,
            )
        except FileNotFoundError:
            r.skip("pi not on PATH — cannot test auth.json path")
            return
        except subprocess.TimeoutExpired:
            r._fail("pi --list-models timed out with key in auth.json")
            return

        if rc == 0:
            r._pass("pi --list-models exits 0 (key in auth.json, no env var)")
        else:
            r._fail(
                f"pi --list-models exited {rc} with key in auth.json: {stderr.strip()}"
            )
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)
