# Vulnerability and secret scanning

Three independent scanners run continuously in this template, each
covering a different blast radius:

| Tool                                                                            | Looks at                                          | Where it runs                | Blocking?              |
| ------------------------------------------------------------------------------- | ------------------------------------------------- | ---------------------------- | ---------------------- |
| [`pip-audit`](https://pypi.org/project/pip-audit/)                              | Python runtime deps vs PyPA advisory DB           | pre-commit + CI `make audit` | **yes**                |
| [`gitleaks`](https://github.com/gitleaks/gitleaks)                              | Secrets in the diff (pre-commit) + history (CI)   | pre-commit + CI              | **yes**                |
| [`trivy`](https://github.com/aquasecurity/trivy) (4 tiers — see below)          | Python deps, IaC misconfig, base-image OS CVEs    | CI (+ local make targets)    | tiers 1 & 4 only       |

Plus a **CycloneDX SBOM** is produced on every CI run and kept as an
artifact for a year, so past releases can be re-scanned against future
CVE drops.

This file documents how all of them fit together, the noise-mitigation
strategy (no scanner is useful if the team has trained itself to ignore
its output), and the `.trivyignore` policy that keeps suppression
deliberate rather than convenient.

## Quick reference

| You want to…                                  | Run                                       |
| --------------------------------------------- | ----------------------------------------- |
| Audit Python deps locally                     | `make audit`                              |
| Scan for secrets locally                      | `make find-secrets`                       |
| Strict Trivy fs scan (CI equivalent)          | `make trivy`                              |
| Broad Trivy fs scan (everything)              | `make trivy-full`                         |
| Trivy scan of a built image                   | `make trivy-image IMAGE=<ref>`            |
| Produce a fresh SBOM                          | `make sbom` → `sbom.cdx.json`             |
| Verify `.trivyignore` policy compliance       | `make trivyignore-check`                  |

---

## `pip-audit`: Python deps vs PyPA advisory DB

Runs against runtime dependencies declared in `pyproject.toml` /
`uv.lock`. Uses the PyPA-curated advisory database (so Python-specific
context, not raw NVD), and is **blocking** in both pre-commit and CI.

Configuration: `PIP_AUDIT_IGNORE` in [`Makefile`](../../Makefile) holds
the small allowlist of accepted vulnerabilities (one entry today —
`PYSEC-2022-42969` — with the rationale inline). Add new entries with
`--ignore-vuln <ID>` and a comment explaining *why*.

Why `pip-audit` despite also having Trivy: it runs without Docker,
uses a Python-specific DB (lower false-positive rate for PyPI deps
than Trivy's NVD lens), and finishes in under a second — cheap enough
to land in `make check` and the pre-push hook without slowing
anything down.

---

## `gitleaks`: secret scanning

Two trigger points:

1. **Pre-commit** (`.pre-commit-config.yaml`): scans the diff before
   the commit lands. Catches "I'm about to commit my `.env`" cases.
2. **CI** (`.gitlab/ci/security.yml`): scans the **full repo + git
   history**. Catches anything that slipped past pre-commit (most
   commonly because a contributor disabled local hooks).

Configuration: [`.gitleaks.toml`](../../.gitleaks.toml). Default rule
set is the upstream one, add `[[rules]]` entries for project-specific
secret patterns (API keys with distinctive prefixes, etc.) when you
know them.

If gitleaks finds a real secret, **rotate it first, then remove it
from history** — even after a `git filter-repo` rewrite, anything that
hit a public forge is presumed compromised.

---

## Trivy: the 4-tier scan model

Vulnerability scanning is loud and noisy by default. The CVE ecosystem
files thousands of advisories a year against transitive dependencies,
most of which are either not reachable in your usage, already
mitigated by your deployment, or theoretical. A flat `trivy fs .` on a
real repo can report dozens of findings on day one, and the natural
response, that is, accepting the noise, gradually leads everyone to ignore
the scan output entirely.

The template addresses this with a **four-tier scan model** plus a
**suppressions file with mandatory justification and expiry**.

### Tier 1: strict fs scan (blocking)

- **CI job:** `trivy:` in [`.gitlab/ci/security.yml`](../../.gitlab/ci/security.yml).
- **Local:** `make trivy`.
- **Driven by:** [`trivy.yaml`](../../trivy.yaml).
- **Policy:**
  - HIGH + CRITICAL only
  - Runtime dependencies only (`skip-dev-deps: true`)
  - `exit-code: 1` → **blocks the pipeline** on findings

This is the build-blocking gate. It is deliberately narrow so that
passing it actually means something — anyone who's run a "block on
everything LOW–CRITICAL" scanner in production knows how quickly the
team stops reading scanner output when every release has 47 findings.

### Tier 2: broad fs scan (informational)

- **CI job:** `trivy-full-report:` in `security.yml`.
- **Local:** `make trivy-full`.
- **Driven by:** *not* `trivy.yaml` (uses `--config-file /dev/null`).
- **Policy:**
  - All severities (LOW + MEDIUM + HIGH + CRITICAL)
  - Dev dependencies included
  - `allow_failure: true` in CI / `--exit-code 0` locally → **never
    blocks**, surfaces as a yellow warning in the pipeline UI

Surfaces what the strict scan filters out so you can triage
proactively (renovate-bump it, or `.trivyignore` it with an expiry)
rather than discovering it the day a previously-LOW finding gets
escalated to HIGH.

### Tier 3: SBOM artifact

- **CI job:** `sbom:` in `security.yml`.
- **Local:** `make sbom` → `sbom.cdx.json`.
- **Format:** CycloneDX (industry standard, scanner-portable).
- **Retention:** 1 year as a CI artifact.

The point isn't scanning *now* but being
able to re-scan a *past release* against tomorrow's vulnerability
database:

```bash
# Six months from now, when CVE-2026-XYZ drops against pydantic 2.x:
trivy sbom sbom.cdx.json
```

This instantly answers *"which of my past releases contain affected
versions?"* without re-cloning or rebuilding anything. It's also the
deliverable that EU CRA, US EO 14028, and SLSA L3 compliance regimes
increasingly require.

### Tier 4: image scan (post-build, blocking)

- **CI job:** `trivy-image:` in [`.gitlab/ci/image-scan.yml`](../../.gitlab/ci/image-scan.yml).
- **Local:** `make trivy-image IMAGE=<ref>`.
- **Scope:** the **built Docker image** — base-image OS packages,
  bytecode artifacts, anything resolved at `docker build` time.
- **Policy:** HIGH + CRITICAL only, same `.trivyignore`, **blocks**
  signing via `needs:` (a failing scan stops `cosign-sign:` from
  running; the image is in the registry but unsigned, so `cosign
  verify` rejects it).

Tiers 1–3 all scan the **source repo**: they see `pyproject.toml`,
`uv.lock`, IaC files. They cannot see what lands in the runtime image
(base-image `libc`, `openssl`, `zlib`, `ca-certificates`, anything
`apt-get` pulls in). Tier 4 closes that gap.

Output is also a GitLab-native `container_scanning` report so findings
appear in the MR security widget and the project's Vulnerability
Report. The job additionally emits `cosign-vuln.json`, consumed by
`cosign-sign:` to attach the scan result as a **signed in-toto
attestation** — see [`sigstore.md`](sigstore.md#whats-signed-and-what-each-signature-buys-you).

### Why four tiers and not one

Scanner output that always blocks teaches people to suppress
aggressively ("just to unblock the release"). Scanner output that
never blocks gets ignored entirely. The split keeps:

- The **blocking** gates (tiers 1 & 4) narrow enough to respect.
- The **informational** view (tier 2) visible without being a release
  blocker.
- The **audit** trail (tier 3) reusable months later.
- The **dual scope** (fs vs image) so the supply-chain attack surface
  on either side is covered.

`pip-audit` is a *fifth*, lighter-weight gate covering the same
runtime-deps slice as tier 1 but without Docker — belt and braces,
and it runs in `make check` so the pre-push hook catches it before
CI does.

---

## `.trivyignore`: accepted-risk policy

Triaged-but-accepted CVEs live in [`.trivyignore`](../../.trivyignore)
at the repo root. The format and policy are enforced mechanically:

```text
# Justification: <why this is acceptable in our context>
CVE-2024-12345 exp:2026-06-30
```

The expiry mechanism (`exp:YYYY-MM-DD`) is **enforced by Trivy itself**:
past that date, the CVE reappears in scan output. The other half of
the policy — *every entry must carry a justification comment on the
preceding non-empty line* — is enforced by
[`scripts/check_trivyignore.py`](../../scripts/check_trivyignore.py),
wired into pre-commit as the `trivyignore-check` hook and into
`make trivyignore-check` so CI catches it too.

The checker rejects:

- Entries without an `exp:YYYY-MM-DD` suffix
- Entries where the preceding non-empty line is **not** a `#` comment
- Malformed CVE / GHSA IDs or unparsable dates

**Six months** is the suggested default expiry — long enough that
you're not re-triaging every sprint, short enough that abandoned
advisories don't silently accumulate. The checker prints a suggested
expiry date in its error output to make adding a compliant entry fast.

### Why this matters

The default "just add the ID to the ignore file" workflow rots
quickly:

- Someone adds an ignore at 3am to unblock a release.
- A year later nobody remembers *why* it was accepted.
- The "ignore" silently absorbs new variants of the same class of bug.
- A scanner upgrade reveals 30 historic ignores and the team gives
  up and ignores the whole file.

The justification-plus-expiry policy forces every entry through a
deliberate triage: *what's the threat?*, *why is it not reachable in
our deployment?*, *when do we re-check?*. If you can't answer those
three questions, you can't suppress the finding.

### When `.trivyignore` isn't enough

For larger teams, regulated environments, or downstream consumers
that need to see your triage rationale, migrate per-CVE justifications
from `.trivyignore` comments into proper
[OpenVEX](https://github.com/openvex/spec) documents. VEX statements
are:

- Machine-readable (JSON schema)
- Scanner-portable (Trivy, Grype, Snyk all consume them)
- The format downstream consumers (government, enterprise security
  teams) expect

`.trivyignore` is the in-repo convenience version. VEX is the
distribution-ready version. Both can coexist.

---

## Continuous maintenance: Renovate

Scanning catches *known* CVEs. Renovate is what keeps the deps moving
*before* a CVE lands against you.

The config lives in [`renovate.json`](../../renovate.json) and the CI
schedule wiring in
[`.gitlab/ci/renovate.yml`](../../.gitlab/ci/renovate.yml). For
operational details (token setup, schedule creation, what's grouped,
what's pinned) see the "Renovate" section in `docs/REPO_SETUP.md` if
it's still around, or upstream
[docs.renovatebot.com](https://docs.renovatebot.com/).

Two settings worth understanding in the security context:

- `vulnerabilityAlerts.schedule: "at any time"` — bypasses the weekly
  schedule when a vuln lands against one of your deps. Critical-CVE
  PRs open within hours, not "next Monday 4am UTC".
- `packageRules.matchManagers: ["dockerfile", "docker-compose",
  "gitlabci"].pinDigests: true` — auto-converts mutable tags like
  `python:3.13-slim` into `python:3.13-slim@sha256:...`. Without
  this, an attacker who compromises Docker Hub could re-push a
  malicious image under the same tag and you'd pull it on the next
  build.

---

## Removing or replacing layers

| Layer       | If you don't need it…                                                                                                                                                                |
| ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `pip-audit` | Drop the pre-commit hook + the `audit:` CI job + the `make audit` target. Trivy fs covers the same ground (with NVD instead of PyPA — usually noisier).                              |
| `gitleaks`  | Drop the pre-commit hook + the `gitleaks:` CI job. Strongly discouraged — even private repos leak credentials when contributors fork them.                                          |
| Trivy fs    | Drop `trivy:` + `trivy-full-report:` + the `make trivy` / `make trivy-full` targets. Keep `pip-audit` as the dep-CVE gate. You lose IaC misconfig detection.                         |
| Trivy image | Drop `trivy-image:`. **Also drop the `cosign attest --type vuln` step** in `sign.yml` (it depends on the cosign-vuln predicate this job emits). The signed scan claim is then gone.  |
| SBOM        | Drop the `sbom:` job + `make sbom`. You lose the ability to re-scan past releases against future CVEs.                                                                                |
| `.trivyignore` policy | Drop `check_trivyignore.py` + its pre-commit hook + `make trivyignore-check`. Trivy still honours the file — you just lose the justification + expiry enforcement.        |

Replace rather than remove if you can — almost every layer addresses a
threat class that exists regardless of which tool catches it.
