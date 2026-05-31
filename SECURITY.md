# Security Policy

## Reporting a vulnerability

**Please do not open a public issue for security bugs.** A public issue
turns into a zero-day disclosure the moment it lands in the tracker.

Report privately via one of:

- **Git Platform Security Advisory** (preferred, both GitHub and GitLab support this)
- **Email:** `<security@example.com>` (CC at least one maintainer for
  redundancy)
- **Encrypted email (optional):** PGP key fingerprint
  `0000 0000 0000 0000 0000  0000 0000 0000 0000 0000 0000`
  (key at `https://example.com/security.asc`)

We aim to:

- Acknowledge your report within **3 business days**
- Send a status update at least once per week thereafter
- Coordinate a disclosure timeline with you, targeting **≤ 90 days**
  from first report (sooner if a fix lands sooner)

> Replace the contact placeholders above before publishing the repo.
> Unreachable contacts are worse than none => researchers will fall back
> to public disclosure.

## Verifying releases

Every release publishes a Docker image signed with Sigstore (keyless,
via cosign). Before relying on a release in production, verify the
signature, full instructions in
[`docs/security/sigstore.md` § Verification](docs/security/sigstore.md#verification).

Each image also ships:

- A CycloneDX **SBOM** attached as an OCI 1.1 referrer
- A SLSA build **provenance** attestation (`mode=max`)

Both are discoverable via the registry's referrers API.

## Supported versions

| Version       | Supported           |
| ------------- | ------------------- |
| Latest tagged | Yes                 |
| Older tags    | No (please upgrade) |
| `main` branch | Best-effort         |

We do not backport security fixes to historical versions. The lockfile
(`uv.lock`) is updated regularly via Renovate, please track the latest
tagged release for the strongest guarantees.

## Scope

**In scope**

- Code in `src/`
- The official Docker image and its attestations
- The CI/CD pipeline (`.gitlab/ci/`, `.gitlab-ci.yml`)
- Dependency / build configuration (`pyproject.toml`, `uv.lock`,
  `Dockerfile`, `renovate.json`, `trivy.yaml`, `openvex.json`)
- The supply-chain tooling (`scripts/verify_image.py`, `scripts/check_vex.py`, `scripts/py_audit_ignores_from_vex.py`)

**Out of scope**

- Vulnerabilities in **transitive dependencies** with no upstream fix
  yet — please report those to the upstream maintainer. We track them
  via Trivy + py-audit and apply fixes as upstream patches land.
- Findings against `tests/`, `docs/`, `wiki/`, or other non-shipped
  paths.
- Issues that require an attacker to already have local file-system
  access, root, or maintainer credentials.
