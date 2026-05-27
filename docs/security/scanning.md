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
its output), and the **OpenVEX policy** that keeps suppression
deliberate rather than convenient — one machine-readable, scanner-
portable, signed document shared by every gate above.

## Quick reference

| You want to…                                  | Run                                       |
| --------------------------------------------- | ----------------------------------------- |
| Audit Python deps locally                     | `make audit`                              |
| Scan for secrets locally                      | `make find-secrets`                       |
| Strict Trivy fs scan (CI equivalent)          | `make trivy`                              |
| Broad Trivy fs scan (everything)              | `make trivy-full`                         |
| Trivy scan of this project's Docker image     | `make trivy-image` (builds, then scans)   |
| Produce a fresh SBOM                          | `make sbom` → `sbom.cdx.json`             |
| Verify the OpenVEX policy compliance          | `make vex-check`                          |

---

## `pip-audit`: Python deps vs PyPA advisory DB

Runs against runtime dependencies declared in `pyproject.toml` /
`uv.lock`. Uses the PyPA-curated advisory database (so Python-specific
context, not raw NVD), and is **blocking** in both pre-commit and CI.

Configuration: suppressions are **not** in the Makefile. They live in
the shared OpenVEX document
([`openvex.json`](../../openvex.json)) at the repo root and are
translated into `--ignore-vuln <ID>` flags at `make audit` time by
[`scripts/pip_audit_ignores_from_vex.py`](../../scripts/pip_audit_ignores_from_vex.py).
See the [OpenVEX section](#the-openvex-accepted-risk-policy) below
for the authoring policy. The shim disappears the day `pip-audit`
adopts native VEX support
([upstream issue](https://github.com/pypa/pip-audit/issues/231)).

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
**single OpenVEX document** that every tier consumes for triage
decisions — controlled-vocab justification, mandatory impact
statement, enforced freshness window.

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
- **Driven by:** CLI flags on the `make trivy-full` / `trivy-full-report:` command
  (override `trivy.yaml`'s HIGH/CRITICAL + runtime-only scope).
- **Policy:**
  - All severities (LOW + MEDIUM + HIGH + CRITICAL)
  - Dev dependencies included (`--include-dev-deps`)
  - `allow_failure: true` in CI / `--exit-code 0` locally → **never
    blocks**, surfaces as a yellow warning in the pipeline UI

Surfaces what the strict scan filters out so you can triage
proactively (renovate-bump it, or add a VEX statement with the right
justification) rather than discovering it the day a previously-LOW
finding gets escalated to HIGH.

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
- **Local:** `make trivy-image` —> runs
  [`scripts/trivy_image_local.py`](../../scripts/trivy_image_local.py),
  which `docker build`s this project's image (tagged
  `<project>-trivy-scan:local`) and scans it with the same OpenVEX policy.
- **Scope:** the **built Docker image** — base-image OS packages,
  bytecode artifacts, anything resolved at `docker build` time.
- **Policy:** HIGH + CRITICAL only, same OpenVEX document, **blocks**
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

## The OpenVEX accepted-risk policy

Triaged-but-accepted CVEs live in a single
[OpenVEX](https://github.com/openvex/spec) document at the repo root,
[`openvex.json`](../../openvex.json). Every scanner in the pipeline
reads from the same file:

- **Trivy** (fs + image) consumes it natively via `--vex openvex.json`.
  See the [Trivy VEX docs](https://trivy.dev/docs/latest/supply-chain/vex/).
- **pip-audit** — which does not yet support VEX natively
  ([upstream issue](https://github.com/pypa/pip-audit/issues/231)) —
  reads the same file through a small stdlib shim
  ([`scripts/pip_audit_ignores_from_vex.py`](../../scripts/pip_audit_ignores_from_vex.py))
  that translates filterable statements into `--ignore-vuln <ID>`
  flags.
- **cosign** signs the document on release as a fifth attestation
  alongside the image, vuln scan, SBOM, and SLSA provenance —
  `cosign attest --type openvex` in
  [`.gitlab/ci/sign.yml`](../../.gitlab/ci/sign.yml). Downstream
  consumers can verify the triage came from this project's CI rather
  than a tampered mirror.

One source of truth, one CVE budget, one signed artifact.

### Document shape

```json
{
  "@context": "https://openvex.dev/ns/v0.2.0",
  "@id": "https://openvex.dev/docs/public/vex-<your-id>",
  "author": "Project Maintainers",
  "timestamp": "2026-05-26T00:00:00Z",
  "version": 1,
  "statements": [
    {
      "vulnerability": {
        "name": "CVE-2024-12345",
        "aliases": ["PYSEC-2024-12345", "GHSA-..."]
      },
      "products": [
        { "@id": "pkg:pypi/<package>" }
      ],
      "status": "not_affected",
      "justification": "vulnerable_code_not_in_execute_path",
      "impact_statement": "What makes this CVE non-applicable HERE (not in the abstract).",
      "timestamp": "2026-05-26T00:00:00Z",
      "last_updated": "2026-05-26T00:00:00Z"
    }
  ]
}
```

Status values (from the OpenVEX spec):

- `not_affected` — vuln does not impact this product; finding is
  filtered out of scan results. Requires `justification` +
  `impact_statement`.
- `affected` — vuln does impact this product; finding stays in scan
  output. Requires `action_statement` describing planned remediation.
- `fixed` — was affected, now patched. Finding is filtered out for
  this version onwards.
- `under_investigation` — triage in progress; finding stays in scan
  output.

Justification controlled vocabulary (for `status: not_affected`):

- `component_not_present`
- `vulnerable_code_not_present`
- `vulnerable_code_not_in_execute_path`
- `vulnerable_code_cannot_be_controlled_by_adversary`
- `inline_mitigations_already_exist`

Pick the one that best fits and explain *why* in `impact_statement`.

### Enforced policy

Validation runs in two complementary halves so each tool does what it's
best at — JSON Schema for structure, Python for local policy:

**1. Structural — upstream OpenVEX JSON Schema**, fetched live from
[`openvex/spec @ main`](https://raw.githubusercontent.com/openvex/spec/main/openvex_json_schema.json)
by the
[`check-jsonschema`](https://github.com/python-jsonschema/check-jsonschema)
pre-commit hook (alias `vex-schema`). The fetched schema is cached
under `~/.cache/check-jsonschema/` with ETag revalidation, so the
network cost is a single HEAD request per run after the first fetch.
Coverage:

- Well-formed JSON, OpenVEX `@context` URI, document-level required
  fields (`@id`, `author`, `timestamp`, `version`, `statements`),
  `additionalProperties: false` everywhere (typos in field names are
  rejected at commit time, not silently ignored).
- Each statement carries a `vulnerability` object with `name` and an
  array of unique `aliases`, plus at least one `products` entry with
  a valid IRI `@id` or a `purl`/`cpe22`/`cpe23` identifier.
- Enum-validated `status` (one of `not_affected` / `affected` /
  `fixed` / `under_investigation`) and `justification` (one of the
  five OpenVEX values).
- Conditional rules: `not_affected` requires `justification` OR
  `impact_statement` (we tighten this to AND — see below);
  `affected` requires `action_statement`.
- All timestamps must be RFC 3339 / ISO 8601 (`format: date-time`).

By delegating to the upstream schema we get spec-correctness for free
and stay in lock-step with the standard — adopters reading the OpenVEX
docs see the same rules the linter enforces, with no project-specific
re-interpretation in between. The trade-off: the hook needs network
access (an airgapped CI agent can't reach
`raw.githubusercontent.com`), and a future upstream patch lands
automatically rather than via PR. We pin to `main` rather than a tag
because OpenVEX's tagging predates the schema file and the
`openvex.dev/ns/v0.2.0/openvex_json_schema.json` URL the spec docs
suggest currently redirects to the GitHub repo HTML page rather than
serving the schema.

**2. Local-policy — [`scripts/check_vex.py`](../../scripts/check_vex.py)**
(applied by the `vex-freshness` pre-commit hook). Covers what JSON
Schema can't express:

- **Freshness window:** every statement was re-triaged within the
  last **180 days** (computed at check time against the statement's
  `last_updated`, falling back to the document `timestamp`). Past
  that, the checker fails and the statement must either be refreshed
  (bump `last_updated` to today) or removed.
- **Stricter `not_affected` rule:** the spec accepts `justification`
  OR `impact_statement`; we require **both**, so project-specific
  reasoning ("we don't import `py.path`") can't be silently dropped
  behind a rubber-stamped controlled-vocab value.

Both halves run via `make vex-check` (which CI executes as part of
`make repo-check`) and as pre-commit hooks when the OpenVEX document
or the local checker is staged.

### Why this matters

The default "just add the ID to the ignore file" workflow rots
quickly:

- Someone adds an ignore at 3am to unblock a release.
- A year later nobody remembers *why* it was accepted.
- The "ignore" silently absorbs new variants of the same class of bug.
- A scanner upgrade reveals 30 historic ignores and the team gives
  up and ignores the whole file.

OpenVEX forces every entry through a deliberate triage: *what's the
threat?* (the vuln id), *why is it not reachable in our deployment?*
(controlled-vocab justification + free-text impact statement), *when
do we re-check?* (180-day freshness window enforced mechanically).
If you can't answer those three questions, you can't suppress the
finding.

### Downstream consumption

The `openvex.json` document is the engineer-facing source of truth,
not the org-wide governance system. Aggregating across projects,
publishing to a central platform (Sonatype IQ, GUAC, DependencyTrack,
Mend, Snyk, …), and exporting to compliance formats (CSAF VEX, hosted
VEX repository) are covered in [`vex.md`](vex.md).

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
| `pip-audit` | Drop the pre-commit hook + the `audit:` CI job + the `make audit` target + `scripts/pip_audit_ignores_from_vex.py`. Trivy fs covers the same ground (with NVD instead of PyPA — usually noisier) and consumes the OpenVEX document natively, so suppressions don't move.|
| `gitleaks`  | Drop the pre-commit hook + the `gitleaks:` CI job. Strongly discouraged — even private repos leak credentials when contributors fork them.                                          |
| Trivy fs    | Drop `trivy:` + `trivy-full-report:` + the `make trivy` / `make trivy-full` targets. Keep `pip-audit` as the dep-CVE gate. You lose IaC misconfig detection.                         |
| Trivy image | Drop `trivy-image:`. **Also drop the `cosign attest --type vuln` step** in `sign.yml` (it depends on the cosign-vuln predicate this job emits). The signed scan claim is then gone. The `cosign attest --type openvex` step is independent and can stay.|
| SBOM        | Drop the `sbom:` job + `make sbom`. You lose the ability to re-scan past releases against future CVEs.                                                                                |
| OpenVEX policy | Drop `check_vex.py` + its pre-commit hook + `make vex-check`. Trivy still honours the VEX document via `--vex` — you just lose the justification + freshness enforcement.        |

Replace rather than remove if you can — almost every layer addresses a
threat class that exists regardless of which tool catches it.
