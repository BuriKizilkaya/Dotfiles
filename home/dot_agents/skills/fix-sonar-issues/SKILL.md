---
name: fix-sonar-issues
description: |
  Use when asked to fix, resolve, or triage SonarCloud issues on a PR or branch.
  Covers installing sonarqube-cli, fetching issues from SonarCloud, grouping them
  by file and severity, applying code fixes, and verifying the fixes rebuild
  cleanly. Trigger keywords: sonar, sonarcloud, sonar issues, sonar findings,
  code smell, sonar bug, sonar vulnerability, fix sonar, sonar PR, static
  analysis issues.
---

# Fix SonarCloud Issues

This skill uses the official [SonarQube CLI](https://github.com/SonarSource/sonarqube-cli)
to fetch and fix issues raised by SonarCloud against the current PR branch.
Follow the steps in order and do not skip any.

---

## Step 1 — Confirm prerequisites

1. `sonarqube-cli` is declared in `mise.toml` and installed:
   ```bash
   mise install          # installs sonarqube-cli if not already present
   sonar --version
   ```

2. Authentication — the CLI uses the `SONARQUBE_CLI_TOKEN` and
   `SONARQUBE_CLI_ORG` environment variables for non-interactive / agent use.
   Never pass a token as a CLI argument or hard-code it in a file.

   ```bash
   # Set these in your shell (or ask the user to provide them):
   export SONARQUBE_CLI_TOKEN=<token>
   export SONARQUBE_CLI_ORG=konplan          # the SonarCloud organization slug
   ```

   Verify:
   ```bash
   sonar auth status
   # Expected: [✓ Connected]
   ```

   If `SONAR_TOKEN` is already set (the CI variable), re-export it:
   ```bash
   export SONARQUBE_CLI_TOKEN=$SONAR_TOKEN
   ```

---

## Step 2 — Fetch issues for the current branch

The project key is read from `sonar-project.properties` automatically when the
CLI is invoked from the repo root. Use `--format toon` for token-efficient
LLM-friendly output, or `--format table` for human-readable terminal output.

```bash
# List open BLOCKER + CRITICAL + MAJOR issues on the current branch:
sonar list issues \
  --severities BLOCKER,CRITICAL,MAJOR \
  --branch "$(git rev-parse --abbrev-ref HEAD)" \
  --format toon
```

> **Note:** The CLI does not expose a `--types` filter. If you need to narrow to
> BUGs / VULNERABILITYs, filter the `toon`/`json` output by the `type` field
> (e.g. with `jq`).

> **Note:** Severity values depend on the server mode. Standard Experience uses
> `MINOR,MAJOR,CRITICAL,BLOCKER`; Multi-Quality Rule (MQR) mode uses
> `LOW,MEDIUM,HIGH,BLOCKER`. If a query errors on severities, use the MQR set.

Key flags:

| Flag | Purpose | Default |
|---|---|---|
| `--project <key>` | Override project key | auto-detected from `sonar-project.properties` (pass explicitly if detection fails) |
| `--branch <name>` | Branch to query | none (must be specified explicitly) |
| `--severities` | Comma-separated severities | all |
| `--format` | `json`, `table`, `toon`, `csv` | `json` |
| `--page-size` | Results per page (max 500) | 100 |

If the command returns zero issues and there are issues visible in the
SonarCloud web UI, verify you are using the correct branch name and that a
scan has completed for that branch.

---

## Step 3 — Analyze local changes (optional, SonarQube Cloud only)

For fast pre-fix feedback on uncommitted edits:

```bash
sonar analyze --base main          # issues introduced vs main
sonar analyze --file src/foo.c     # analyze a specific file
```

This reports only issues *introduced by your changes*, which is useful for
checking that a proposed fix does not introduce a new violation.

---

## Step 4 — Triage and prioritise

For each issue group, categorise by effort:

| Priority | Criteria |
|---|---|
| **Fix immediately** | BLOCKER or CRITICAL BUGs and VULNERABILITYs |
| **Fix in this PR** | MAJOR BUGs / VULNERABILITYs, and CODE_SMELLs in code you authored |
| **Create follow-up** | MINOR / INFO, or MAJOR CODE_SMELLs in unrelated code |

Rules:
- Never suppress an issue with `// NOSONAR` unless it is a documented
  false-positive. When justified, add the reason inline:
  `// NOSONAR: <rule_id> — <reason>. Tracked: <ticket/issue ref>.`
- Never widen a suppression beyond the single offending line.

---

## Step 5 — Apply the fixes

For each issue:

1. Note the rule ID (e.g. `c:S1481`, `c:S3011`). Look up the rule:
   ```bash
   open https://rules.sonarsource.com/c/<rule_id>   # e.g. c/S1481
   ```
   (The CLI has no `list rules` command; the rules site is the source of truth.)

2. Apply the minimal fix. Common patterns for C firmware:

   | Rule family | Typical fix |
   |---|---|
   | Unused variable / parameter | Remove, or `(void)param;` cast |
   | Missing `const` | Add `const` qualifier |
   | Null-pointer dereference | Add `NULL` check before use |
   | Buffer overrun risk | Use bounded functions (`strncpy`, `snprintf`) |
   | Magic number | Extract to a named `#define` or `enum` |
   | Missing `default` in `switch` | Add `default: break;` (or `__ASSERT`) |
   | Dead / unreachable code | Remove or add a comment |
   | Cognitive complexity | Extract sub-functions to reduce nesting |

3. After editing each file, spot-check with:
   ```bash
   sonar analyze --file <path/to/file.c>
   ```

---

## Step 6 — Rebuild and run tests

```bash
mise run build-nrf        # must succeed
mise run unittests        # all tests must pass
mise run check-format     # must exit 0
```

Fix any compilation errors before continuing.

---

## Step 7 — Confirm issue reduction

Re-query to verify the count dropped (full re-analysis happens on the next CI
push; local `sonar analyze` gives immediate feedback on your changes):

```bash
sonar list issues \
  --severities BLOCKER,CRITICAL,MAJOR \
  --branch "$(git rev-parse --abbrev-ref HEAD)" \
  --format table
```

---

## Step 8 — Update release-notes.yml (if applicable)

If the fixes address a user-visible bug or security vulnerability, update
`release-notes.yml` under the appropriate version entry:

```yaml
fixes:
  - <Azure DevOps item id>  # or a short description
```

---

## Checklist

- [ ] `sonarqube-cli` installed (`sonar --version` works).
- [ ] `SONARQUBE_CLI_TOKEN` and `SONARQUBE_CLI_ORG` are set; `sonar auth status` shows `[✓ Connected]`.
- [ ] `sonar list issues` ran without error for the target branch.
- [ ] All BLOCKER and CRITICAL issues fixed (or explicitly justified with `// NOSONAR: <rule> — <reason>`).
- [ ] All MAJOR BUGs and VULNERABILITYs in PR-authored code fixed.
- [ ] No bare `// NOSONAR` without a justification and ticket reference.
- [ ] `mise run check-format` exits 0.
- [ ] `mise run build-nrf` exits 0.
- [ ] `mise run unittests` exits 0.
- [ ] `release-notes.yml` updated if a user-visible bug or vulnerability was fixed.
