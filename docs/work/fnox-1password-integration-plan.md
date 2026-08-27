# Plan: fnox + 1Password development secrets

## Goal
Provide Pi, OpenCode, and developer CLI API tokens from a dedicated 1Password `Development` vault, including in devcontainers, without committing plaintext credentials or requiring per-command wrappers.

## Approach
Use mise only to install `fnox`. Use fnox as the secrets layer: a tracked `fnox.toml` contains 1Password references and an age-encrypted 1Password service-account token. Shell integration exports resolved values for supported working directories. Pi and OpenCode OAuth sessions remain separate persistent state rather than fnox secrets.

## Steps

1. **Create and scope the 1Password vault and service account** — Create a `Development` vault, add separate items for OpenCode, model-provider, GitHub, and Azure DevOps credentials, and create a service account limited to this vault.
   - Files: none
   - Notes: use minimum-scoped GitHub and Azure DevOps tokens. The service-account token is a bootstrap credential and must never be committed in plaintext.

2. **Create the age identity and record its public recipient** — Generate a dedicated age identity for fnox (not an existing SSH private key), retain its private identity outside Git, and capture the public `age1...` recipient.
   - Files: local-only age identity, e.g. `~/.config/fnox/age.txt`
   - Notes: the private identity will be supplied to development machines and devcontainers as `FNOX_AGE_KEY` or an equivalent protected file/secret mount. Only the public recipient may be committed.

3. **Add fnox to the managed mise toolchain** — Add a pinned `fnox` version to the common mise configuration so the existing chezmoi `mise install` lifecycle installs it on supported platforms.
   - Files: `home/dot_config/mise/conf.d/common.toml`
   - Tests: extend `tests/helpers/core.py` to assert the configured tool; add a CLI assertion if the Docker image can install it reliably.
   - Notes: pin the first tested version instead of using `latest` to keep devcontainer builds reproducible.

4. **Add a safe, tracked fnox configuration** — Add a chezmoi-managed `fnox.toml` containing the age provider, the 1Password provider for vault `Development`, an age-encrypted `OP_SERVICE_ACCOUNT_TOKEN`, and `op://Development/...` references for required environment variables.
   - Files: new `home/fnox.toml` (renders to `~/fnox.toml`) or another discovery-compatible location chosen in step 5
   - Tests: assert that the rendered config exists and contains providers/references, but never assert or log resolved values.
   - Notes: commit only public recipients, encrypted ciphertext, and 1Password references. Do not add `AGE-SECRET-KEY`, `ops_...`, API keys, or a private key file.

5. **Decide and implement the configuration discovery scope** — Verify fnox’s config discovery for normal host projects and the repository path used by devcontainers. Place `fnox.toml` where it covers the intended directories, or use per-project configs that inherit a common config.
   - Files: potentially `home/fnox.toml`; potentially documented setup for project-level `fnox.toml`
   - Notes: a config in `~` is discovered only for directories below `$HOME`; common devcontainer workspaces such as `/workspaces/...` may need their own config strategy.

6. **Enable fnox shell integration safely** — Add guarded activation after mise activation in Bash and Zsh so entering a configured directory loads the secret environment and leaving removes it.
   - Files: `home/dot_bashrc`, `home/dot_zshrc`
   - Tests: add rendered-content assertions and a non-interactive shell smoke test that confirms shell startup still succeeds when `FNOX_AGE_KEY` is absent.
   - Notes: configure quiet output if prompt messages are undesirable. Missing credentials must not break ordinary shells or the Docker test environment.

7. **Define devcontainer bootstrap and persistence** — Document or add the devcontainer-specific mechanism that supplies the age identity without committing it: a Docker secret, protected bind mount, or manually exported `FNOX_AGE_KEY`. Use named volumes for Pi and OpenCode OAuth state if subscription login is used.
   - Files: documentation; project devcontainer configuration only if this repository owns it
   - Notes: do not mount the host’s full 1Password session or full `~/.pi/agent` into an untrusted container. The `Development` service account must have access only to the dedicated vault.

8. **Verify the complete no-secret path** — Run the existing devcontainer test suite with no credentials, then manually validate fnox resolution on a trusted machine/container with `FNOX_AGE_KEY` supplied.
   - Files: `tests/helpers/core.py`, potentially a new fnox-specific helper
   - Commands: `bash tests/run-tests.sh`; `fnox export --format json` (manual, do not paste output into logs)
   - Notes: validate only variable names and command exit status in automated tests; live 1Password resolution remains a manual opt-in check.

## Dependencies between steps
- Step 1 must precede encrypting the service-account token in step 4.
- Step 2 must precede step 4 and devcontainer bootstrap in step 7.
- Steps 3–5 must be complete before enabling shell activation in step 6.

## Out of scope
- Storing Pi or OpenCode OAuth refresh tokens in 1Password.
- Sharing host 1Password desktop sessions or SSH-agent sockets with devcontainers.
- Adding plaintext credentials to chezmoi templates, tests, CI logs, or Git.

## Open questions
- Are all intended workspaces below `$HOME`, or do devcontainers work from `/workspaces`? This determines the fnox config-discovery layout.
- Does the 1Password account plan support a scoped service account? If not, use age-encrypted static development tokens or interactive `op` authentication instead.
- Which provider variables are actually needed initially (for example `OPENCODE_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GITHUB_TOKEN`, and `AZURE_DEVOPS_EXT_PAT`)?
- Which protected delivery mechanism should provide `FNOX_AGE_KEY` to a devcontainer?

## Estimated complexity
Medium: the repository changes are small, but secure bootstrap, config discovery, and no-credential test behavior need validation across host and devcontainer environments.
