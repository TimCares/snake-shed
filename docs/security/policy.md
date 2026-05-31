# Policy and governance

Technical controls (scanning, signing) only matter if there's a
matching **process** around them: a way for outsiders to report bugs
without immediately publishing them, a way to keep insiders from
quietly bypassing the controls, and platform-level settings that
cement the rules at the GitLab / GitHub project level.

This file covers the three governance pieces this template ships:

| Topic                                                                 | Lives at                                          | Status                                  |
| --------------------------------------------------------------------- | ------------------------------------------------- | --------------------------------------- |
| Vulnerability disclosure                                              | [`SECURITY.md`](../../SECURITY.md)                | Template; **edit before publishing**    |
| Reviewer gating on security-sensitive paths                           | [`CODEOWNERS`](../../CODEOWNERS)                  | Template; **edit before relying on it** |
| CI / runner hardening                                                 | Project-level UI settings (this doc)              | Manual one-time setup per project       |

Everything except the first two **cannot** be expressed in version controlled files,
GitLab / GitHub deliberately keep these as
project-level UI knobs so they can't be modified by a malicious push
to the default branch. This doc is the runbook for getting them set
correctly.

---

## Vulnerability disclosure (`SECURITY.md`)

[`SECURITY.md`](../../SECURITY.md) at the repo root documents:

- **How to privately report** a security bug (GitLab Security
  Advisory, email fallback, optional PGP).
- **Response SLA targets** (3 business days to acknowledge, ≤ 90
  days to disclose).
- **Scope** — which paths are in / out.
- **How to verify a release** (pointer to
  [`sigstore.md`](sigstore.md#verification)).

Both GitLab and GitHub render `SECURITY.md` automatically on the
repo page and link to it from the issue tracker, which redirects
researchers away from filing a public issue that becomes an instant
0-day.

### Action item before publishing

The shipped file uses **placeholder values**:

- `<security@example.com>` for the disclosure email.
- A dummy PGP fingerprint (`AAAA BBBB CCCC ...`).

Replace these with real values before the repo goes public. **An
unreachable contact is worse than none** — researchers will fall
back to public disclosure (Twitter, mailing lists, blog posts) when
they can't reach you, which means your first warning is the same
warning everyone else gets.

### Recommended additions (per project)

The shipped file is intentionally minimal. Consider adding, project-
by-project:

- **Severity definitions** (CVSS thresholds → response SLA) if the
  default "3 days / 90 days" doesn't fit.
- **Public preferred disclosure path** if you want to favour
  GitLab's [Security Advisory](https://docs.gitlab.com/ee/user/project/repository/security_advisories.html)
  or GitHub's [Private Vulnerability Reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
  over email. Both produce a private collaboration space the
  reporter and your team can use; both can issue CVEs.

---

## Code ownership (`CODEOWNERS`)

[`CODEOWNERS`](../../CODEOWNERS) at the repo root maps security-
sensitive paths to **required reviewers**. Without it, anyone with
push rights can quietly change `Dockerfile`, `renovate.json`,
the OpenVEX document, `.gitlab/ci/sign.yml`, etc.
by piggybacking on an unrelated MR. CODEOWNERS
ensures those paths get a second pair of eyes from someone who knows
what to look for.

### Paths covered in the shipped file

- `.gitlab/ci/*.yml` — CI pipeline (anything here can sign / push /
  release).
- `Dockerfile`, `docker-compose.yaml` — runtime image surface.
- `trivy.yaml`, `openvex.json` — vulnerability scanning config and
  accepted-risk OpenVEX document.
- `renovate.json` — dependency update policy.
- `pyproject.toml` (runtime deps section) — runtime surface.
- `scripts/verify_image.py`, `scripts/check_vex.py`,
  `scripts/py_audit_ignores_from_vex.py` — verify / VEX enforcement /
  py-audit adaption.
- `SECURITY.md`, `CODEOWNERS` itself — policy files.
- `docs/security/**` — this directory (so security docs don't drift
  from the implementation behind a security-team-blind merge).

### Action item before relying on it

The shipped file uses **placeholder owners** (`@security-team`,
`@platform-team`, `@maintainers`). Replace them with real GitLab /
GitHub usernames or groups.

**Both platforms silently treat unknown owners as "no required
reviewer".** The file *looks* valid, the MR view *looks* like it
respects code ownership, but in fact unknown handles produce zero
enforcement. Verify by:

- Opening an MR that touches a CODEOWNERS-protected path.
- Confirming the "approved by code owner" indicator activates only
  when one of the listed owners approves.

If you see the indicator turn green without an owner approving,
your placeholders aren't resolving — fix them before merging
anything sensitive.

### Make it required, not advisory

CODEOWNERS only **suggests** reviewers by default. To make code-owner
approval an actual merge gate:

- **GitLab:** Settings → Repository → Protected branches → on your
  default branch, tick *"Require approval from code owners"*.
- **GitHub:** Settings → Branches → Branch protection rules → on
  your default branch, tick *"Require review from Code Owners"*.

Both also support [last-match-wins](https://docs.gitlab.com/ee/user/project/codeowners/reference.html#patterns)
semantics: when several patterns match the same file, only the
**last** matching pattern applies. The shipped file is ordered with
the most specific patterns last so the most relevant team is the one
gated on; review the order if you reshuffle entries.

---

## CI / runner hardening

A few GitLab-specific settings to lock down once the template is
forked into a real project. None of these can be expressed in code,
so they have to be configured per-instance in the project UI.

### Restrict `CI_JOB_TOKEN` scope

By default, `CI_JOB_TOKEN` can read package registries and container
registries of **other** projects in the same GitLab group. A
compromised runner job could exfiltrate proprietary code from
sibling projects without ever leaving the GitLab API — no DNS
egress, no logs, no obvious smoking gun.

Lock it down in **Settings → CI/CD → Job token permissions →
*"Limit access from this project"***: explicitly list the projects
that genuinely need to consume this project's artifacts (usually
none). Configure the inverse list too (*"Limit access to this
project"*) to restrict which projects can pull from yours.

A reasonable default for a brand-new project is:

- **From** this project: empty list.
- **To** this project: just this project.

You can always relax the rule as legitimate cross-project
dependencies appear.

### Protect the default branch

**Settings → Repository → Protected branches → on your default
branch**:

| Setting                                | Recommended                                    |
| -------------------------------------- | ---------------------------------------------- |
| Allowed to push                        | **No one** (force everything through MRs)      |
| Allowed to merge                       | Maintainers                                    |
| Require approval from code owners      | **On**, with real `CODEOWNERS` entries          |
| Code owner approval required for       | All paths                                       |

The combination of "no direct push" + "require code-owner approval"
+ a populated `CODEOWNERS` means a single compromised account
cannot ship a release. They can open an MR, but it can't merge
without a second human approving.

### Protect tags

**Settings → Repository → Protected tags → wildcard `v*`**: only
Maintainers may create.

This stops a compromised developer account from pushing a fake
`v999.0.0` tag that the release pipeline would dutifully version-
bump, sign, and publish. The image would carry a valid Sigstore
signature anchored at this project's CI identity — i.e. it would
*look* legitimate to every consumer's `cosign verify`. Protected
tags are the lock on that footgun.

### Mask + protect sensitive CI variables

**Settings → CI/CD → Variables**: every variable you add should be:

- **Masked** — its value is redacted in job logs.
- **Protected** — it's only injected into jobs running on protected
  branches / tags.

This template doesn't ship any project-specific CI variables, but
expect to add at minimum:

- `RENOVATE_TOKEN` (already documented in `docs/REPO_SETUP.md`).
- A registry-write token if you use a registry outside the built-in
  GitLab one.
- Any cloud-deploy credentials for downstream stages you add.

GitLab refuses to mask values that don't meet its length /
character requirements; if you see "value cannot be masked", the
secret is too short or contains restricted characters — generate a
longer one or wrap it in base64.

### Disable shared runners on sensitive projects

If your project signs releases, builds images, or holds production
secrets, **do not run on GitLab.com's shared runners** for the
sensitive jobs. The shared runners run untrusted code from millions
of projects on the same VM hosts; rootless dind helps, but the
defence-in-depth answer is to run those specific jobs on a runner
you control.

**Settings → CI/CD → Runners**:

- Disable *"Enable shared runners for this project"* (or scope it
  to non-sensitive jobs via `tags:`).
- Register a project-specific or group-specific runner with
  `tags: [trusted]`, then add `tags: [trusted]` to the `docker:`,
  `cosign-sign:`, and `semantic-release:` jobs.

For most internal-team projects, a single small VM running
`gitlab-runner` in Docker-executor mode is enough. For team-of-one
hobby projects, the shared runners are usually fine — but be
aware of what you're trusting.

---

## Future expansion

Topics not currently covered by this template, in rough order of
how likely you are to want them:

- **Signed dev commits + CI verification (gitsign levels 1+2).**
  See [`sigstore.md` → Future expansion](sigstore.md#future-expansion-levels-1-and-2).
- **Hosted VEX repository** for cross-project triage statements. The
  template ships an in-repo OpenVEX document; once you operate
  multiple projects, publish a shared remote VEX repo and point
  Trivy at it with `--vex repo`. See [`vex.md`](vex.md) for the full
  downstream-consumption story (aggregators, central platforms,
  format conversion).
- **Federated identity / org-wide OIDC scoping.** If you operate
  multiple GitLab groups under one organisation, use Sigstore's
  identity regex to enforce "any commit / image signed by anyone
  under `https://gitlab.com/myorg/`" as a single trust policy.
- **Hardware-attested OIDC** via WebAuthn / passkey for the IdP
  itself, so every CI-job OIDC token traces back to a human tap.
  Configurable on every major IdP. See
  [`sigstore.md` -> Hardware-backed identity](sigstore.md#hardware-backed-identity-yubikey-webauthn).
