# Security

This directory documents the supply-chain and runtime security posture
of this project: which threats it defends against, how the defenses are
wired in, and which knobs to turn when your threat model or compliance
regime changes.

## Reading order

| File | Covers |
| ---- | ------ |
| [`README.md`](README.md) (this file) | High-level posture, threat model, the layered defence diagram, where to start. |
| [`scanning.md`](scanning.md) | Vulnerability + secret scanning: Trivy (4 tiers), `pip-audit`, gitleaks, SBOM, the `.trivyignore` policy. |
| [`sigstore.md`](sigstore.md) | Sigstore-anchored signing for images (`cosign`) and commits (`gitsign`), how to verify, and how to operate this with **private artifacts** (self-hosted Sigstore / key-based fallback). |
| [`policy.md`](policy.md) | Repository governance: `SECURITY.md` disclosure policy, `CODEOWNERS` review gating, CI / runner hardening (`CI_JOB_TOKEN` scope, protected branches/tags). |

If you only have five minutes, read this file and the *"Verifying a
release"* section of [`sigstore.md`](sigstore.md#verification).

## The posture in one diagram

Code travels through six layers before it lands in a consumer's
environment; each layer defends a specific failure mode. Lose one and
the others still hold: "**defence in depth**".

```text
┌─────────────────────────────────────────────────────────────────────┐
│  1 · Developer workstation                                          │
│      pre-commit  →  ruff (incl. S=bandit), gitleaks, hadolint,      │
│                     shellcheck, codespell, commitizen, ty,          │
│                     interrogate, pytest, pip-audit, trivyignore     │
│                     policy check                                    │
│      pre-push    →  the full `make check` aggregate (= CI quality)  │
└─────────────────────────────────────────────────────────────────────┘
                                  ↓ git push
┌─────────────────────────────────────────────────────────────────────┐
│  2 · CI quality + security stages                                   │
│      Repeats pre-commit checks on the whole repo (in case dev       │
│      bypassed local hooks), then runs the security suite:           │
│        pip-audit          → Python deps vs PyPA advisory DB         │
│        gitleaks           → full repo history secrets               │
│        trivy fs (strict)  → blocking HIGH/CRITICAL on runtime deps  │
│        trivy fs (broad)   → informational, all severities + dev     │
│        sbom               → CycloneDX artifact, 1-year retention    │
└─────────────────────────────────────────────────────────────────────┘
                                  ↓ on default branch only
┌─────────────────────────────────────────────────────────────────────┐
│  3 · CI release stage                                               │
│      semantic-release  →  versions from conventional commits,       │
│                           writes CHANGELOG, tags, pushes.           │
│                           Release commit + tag are gitsign-signed   │
│                           (Sigstore keyless, anchored at CI OIDC).  │
└─────────────────────────────────────────────────────────────────────┘
                                  ↓ when a release is produced
┌─────────────────────────────────────────────────────────────────────┐
│  4 · CI docker stage  (DAG; each gates the next via `needs:`)       │
│      docker:        rootless dind builds image; pushes via buildx   │
│                     with --sbom=true + --provenance=mode=max;       │
│                     captures IMAGE_DIGEST; extracts SBOM +          │
│                     provenance predicates from the registry.        │
│      trivy-image:   scans the pushed image; emits cosign-vuln       │
│                     predicate; blocks on HIGH/CRITICAL.             │
│      cosign-sign:   cosign sign (image) + 3× cosign attest          │
│                     (vuln, spdx, slsaprovenance), all anchored      │
│                     at CI OIDC identity.                            │
└─────────────────────────────────────────────────────────────────────┘
                                  ↓ image + signatures in registry
┌─────────────────────────────────────────────────────────────────────┐
│  5 · Consumer verification (outside this repo's CI)                 │
│      `make verify-image` / `cosign verify` / `cosign verify-        │
│      attestation` / `gitsign verify` — all keyed off the same       │
│      OIDC identity regex. Admission controllers reuse the policy.   │
└─────────────────────────────────────────────────────────────────────┘
                                  ↓ on container start
┌─────────────────────────────────────────────────────────────────────┐
│  6 · Container runtime                                              │
│      Non-root user (UID 10001), read-only rootfs, cap_drop: ALL,    │
│      no-new-privileges, tmpfs /tmp, resource limits,                │
│      __DISABLE_LOAD_DOTENV__ so secrets never come from baked       │
│      files. See `Dockerfile` + `docker-compose.yaml`.               │
└─────────────────────────────────────────────────────────────────────┘
```

Continuous, sitting alongside all six layers:

- **Renovate** keeps every pin moving (Python deps, container base images,
  pre-commit revs, CI tool versions) and opens **security PRs without
  waiting for the weekly schedule** when a vulnerability lands against a
  used package. See [`scanning.md`](scanning.md#continuous-maintenance-renovate)
  and the project-level [`renovate.json`](../../renovate.json).
- **`CODEOWNERS`** (see [`policy.md`](policy.md#code-ownership-codeowners))
  gates merges into the security-sensitive paths so the layers above
  can't be quietly tampered with.

## Threat model — what each layer covers

| Threat                                                                  | Defended by                                                                                                                  | Where it's documented              |
| ----------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- | ---------------------------------- |
| Dev commits a secret by mistake                                         | gitleaks (pre-commit + CI), `__DISABLE_LOAD_DOTENV__` in image                                                                | [scanning.md](scanning.md#gitleaks-secret-scanning) |
| Python / OS dependency has a known CVE                                  | `pip-audit` + Trivy fs scan (blocking) + Renovate auto-PRs                                                                   | [scanning.md](scanning.md)         |
| Base image has a known CVE                                              | Trivy image scan (blocking on HIGH/CRITICAL) + Renovate `pinDigests`                                                          | [scanning.md](scanning.md#tier-4-image-scan-post-build-blocking) |
| Build step is compromised                                               | Rootless `dind` + cosign-signed SLSA `mode=max` provenance attestation                                                       | [sigstore.md](sigstore.md#whats-signed-and-what-each-signature-buys-you) |
| Registry token leaks from CI logs / `ps aux`                            | `docker login --password-stdin`                                                                                              | `.gitlab/ci/docker.yml`            |
| Someone pushes a malicious image to your registry                       | cosign keyless signature anchored at CI OIDC identity                                                                        | [sigstore.md](sigstore.md#image-signing-cosign) |
| Compromised dev account commits as someone else                         | gitsign on release commits (level 3); levels 1+2 documented for later                                                        | [sigstore.md](sigstore.md#commit-signing-gitsign) |
| Insider sneaks a CI config change past review                           | `CODEOWNERS` + protected branches                                                                                            | [policy.md](policy.md)             |
| Compromised dev account pushes a fake `v999.0.0` tag                    | Protected tags (Maintainer-only)                                                                                              | [policy.md](policy.md#protect-tags) |
| Old release turns out vulnerable months later                           | Signed image-SBOM attestation + `cosign attest --type vuln` (re-checkable forever) + source-repo SBOM CI artifact            | [scanning.md](scanning.md) + [sigstore.md](sigstore.md) |
| Researcher finds a 0-day in production                                  | `SECURITY.md` private disclosure channel                                                                                     | [policy.md](policy.md#vulnerability-disclosure-securitymd) |
| Runtime escape via container vulnerability                              | `cap_drop: ALL` + `no-new-privileges` + non-root user + `read_only`                                                          | [`docker-compose.yaml`](../../docker-compose.yaml) |
| CI runner exfiltrates code from sibling projects in the group           | `CI_JOB_TOKEN` scope restriction (project-level UI setting, not in code)                                                     | [policy.md](policy.md#restrict-ci_job_token-scope) |

No single layer is overkill — each one closes a specific gap the others
can't. An attacker has to defeat **every relevant layer** to succeed; a
defender only has to keep **one** intact to limit blast radius.

## "I just want to verify a release"

You have five independent signed claims to check, all under the same
`--certificate-identity-regexp` + `--certificate-oidc-issuer` policy,
so an admission controller can reuse one trust policy across them.
See [`sigstore.md`](sigstore.md#verification) for full detail and
when to check which.

```bash
IDENTITY="^https://gitlab.com/<your-group>/<your-project>//"
ISSUER="https://gitlab.com"
IMG="registry.gitlab.com/<your-group>/<your-project>@sha256:..."
COMMIT="v1.2.3"  # the release tag

# 1. Image bits are signed by this project's CI
cosign verify --certificate-identity-regexp "$IDENTITY" \
              --certificate-oidc-issuer    "$ISSUER" "$IMG"

# 2. Vulnerability scan claim is signed by this project's CI
cosign verify-attestation --type vuln \
       --certificate-identity-regexp "$IDENTITY" \
       --certificate-oidc-issuer    "$ISSUER" "$IMG"

# 3. SBOM attestation is signed by this project's CI
cosign verify-attestation --type spdx \
       --certificate-identity-regexp "$IDENTITY" \
       --certificate-oidc-issuer    "$ISSUER" "$IMG"

# 4. SLSA provenance attestation is signed by this project's CI
cosign verify-attestation --type slsaprovenance \
       --certificate-identity-regexp "$IDENTITY" \
       --certificate-oidc-issuer    "$ISSUER" "$IMG"

# 5. Release commit is signed by this project's CI
gitsign verify --certificate-identity-regexp "$IDENTITY" \
               --certificate-oidc-issuer    "$ISSUER" "$COMMIT"
```

Five commands, one identity, one trust policy. The image-manifest
signature (1) and the commit signature (5) are the must-check ones
for any deployment; (2)–(4) are post-release auditing claims (*"what
went in"*, *"how was it built"*, *"was it clean at release time"*)
and verify-or-die admission policies typically only gate on (1).

## Operating this with private / internal artifacts

A common worry: *"Sigstore's Fulcio and Rekor are public — does that
leak my internal stuff?"*

Short answer: the **image bits, source code, SBOM contents, and CVE
findings all stay in your private registry**. Rekor only records
hashes, certs, signatures, and timestamps. For most internal projects
that metadata leak is benign. When it isn't, you have a self-hosted
Sigstore option and a key-based fallback.

Full discussion + concrete env-var snippets for both alternatives:
[`sigstore.md` → Using this with private artifacts](sigstore.md#using-this-with-private-artifacts).

## What lives where, briefly

```text
.gitlab/ci/
├── base.yml          stages, .uv-base, RENOVATE skip rule
├── quality.yml       lint / format / type / docstring / spell / shell
├── test.yml          pytest + coverage
├── security.yml      pip-audit, gitleaks, trivy fs (strict + broad), sbom
├── release.yml       semantic-release + gitsign install
├── docker.yml        rootless-dind buildx build + push
├── image-scan.yml    trivy image (blocking; emits cosign-vuln)
├── sign.yml          cosign sign + cosign attest --type vuln
├── renovate.yml      scheduled Renovate runner
└── ...

scripts/
├── release.sh             PSR + gitsign setup (CI release commit signing)
├── verify_image.py        pyproject-driven `cosign verify` helper
└── check_trivyignore.py   .trivyignore policy enforcer

repo-root/
├── trivy.yaml             Trivy config (strict severities)
├── .trivyignore           accepted-CVE list (justified, expiring)
├── .gitleaks.toml         secret scan config
├── SECURITY.md            disclosure policy
├── CODEOWNERS             reviewer gating
└── renovate.json          dep-update policy
```

## Replacing or removing layers

Most layers can be swapped or dropped independently:

- **Sigstore → notation / private CA**: see [sigstore.md](sigstore.md#replacing-sigstore).
- **Trivy → grype / snyk / etc.**: replace the scan commands in
  [`.gitlab/ci/security.yml`](../../.gitlab/ci/security.yml) and
  [`.gitlab/ci/image-scan.yml`](../../.gitlab/ci/image-scan.yml);
  the `cosign attest --type vuln` flow accepts any tool that produces
  a `cosign-vuln`-compatible predicate.
- **Renovate → Dependabot**: only relevant if you migrate to GitHub;
  delete `renovate.json` + `.gitlab/ci/renovate.yml`, add
  `.github/dependabot.yml`.
- **Drop all of it**: each file under `docs/security/` calls out what
  to remove if a layer is overkill for your project's threat model.
  The defaults are tuned for "small team, regulated industry,
  internal product".
