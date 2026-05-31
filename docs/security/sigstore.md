# Sigstore signing (cosign + gitsign)

This template signs **six things**, all rooted in
[Sigstore](https://www.sigstore.dev/), all anchored to the same CI
OIDC identity:

```text
CI job OIDC identity (issued by GitLab to a specific job on the
                       default branch of this specific project)
  ├─ signs the release commit + tag                        ← gitsign
  ├─ signs the released image manifest                     ← cosign sign
  ├─ signs the vuln-scan claim for that image              ← cosign attest --type vuln
  ├─ signs the image SBOM                                  ← cosign attest --type spdx
  ├─ signs the SLSA build provenance                       ← cosign attest --type slsaprovenance
  └─ signs the OpenVEX accepted-risk document              ← cosign attest --type openvex
```

An auditor verifies all six with the **same identity regex** and
gets a single, consistent trust statement: *"signed by this project's
CI on the default branch."*

## Why Sigstore

The traditional alternative is **key-based signing**: generate a long-
lived signing key, store it somewhere (HSM, KMS, file), guard it
forever. Problems:

- The key is a high-value target. Compromise = silent forgery.
- Rotation is painful. Old signatures point at a key that no longer
  exists; new signatures point at a key consumers have to learn
  about.
- Provenance is weak. The signature says "someone with the key
  signed this", not "this CI job, in this project, on this date,
  signed this". You bolt that on out-of-band, if at all.

**Sigstore keyless signing** flips this:

- No long-lived key exists. Each signing event generates a fresh
  ephemeral key, uses it once, and destroys it.
- Identity comes from an **OIDC token** (GitLab issues one to each
  CI job). The CA (Fulcio) exchanges that token for a short-lived
  x509 cert that encodes *which job ran the signing*.
- Every signing event is logged in **Rekor**, a public append-only
  transparency log. Months later, you can still verify a signature
  by checking the cert against the Rekor entry — no key custody
  needed.

Net effect: signing becomes a property of *who ran the job*, not
*who holds the key*. Compromising a runner doesn't get you signatures
for *this* project unless you can also forge the OIDC identity, which
you can't.

## How keyless signing works (mechanics, 30 seconds)

Identical for cosign (images, attestations) and gitsign (commits):

```text
1. GitLab issues a short-lived OIDC token bound to the CI job's identity.
   Wired by  id_tokens: SIGSTORE_ID_TOKEN: aud: sigstore  in the job.

2. The signer (cosign / gitsign) exchanges that token at Fulcio
   (Sigstore's CA) for an x509 cert valid ~10 minutes. The cert's
   Subject Alternative Names encode the OIDC identity — e.g.
     https://gitlab.com/<group>/<project>//.gitlab-ci.yml@refs/heads/main

3. The cert signs the artifact (image digest / commit hash / DSSE
   attestation envelope).

4. The signing event (cert + signature digest + timestamp) is recorded
   in Rekor, a public append-only transparency log.

5. The ephemeral private key is destroyed. Only the signature + the
   Rekor entry remain.
```

Consumers verifying signatures pass `--certificate-identity-regexp`
(constrains *who* signed) + `--certificate-oidc-issuer` (constrains
*which IdP issued the OIDC token*). The verifier cross-checks the
cert against the Rekor entry; if either was forged after the fact,
verification fails.

---

## Image signing: `cosign`

The `cosign-sign:` job in [`.gitlab/ci/sign.yml`](../../.gitlab/ci/sign.yml)
runs after `docker:` (build + push) and `trivy-image:` (scan), and is
gated on both via `needs:`. A failing build or scan means the image is
in the registry but **unsigned** — and any verifier (including
`make verify-image`) rejects unsigned images.

Five signing operations happen in the same job:

1. **`cosign sign`** the image by digest (not tag — tags can be
   re-pushed, digests can't):

   ```bash
   cosign sign --yes "registry.example.com/foo/bar@sha256:..."
   ```

2. **`cosign attest --type vuln`** the Trivy scan result as a signed
   in-toto attestation:

   ```bash
   cosign attest --yes \
     --predicate cosign-vuln.json \
     --type vuln \
     "registry.example.com/foo/bar@sha256:..."
   ```

   `cosign-vuln.json` is produced by `trivy-image:` (which the
   `cosign-sign:` job pulls in via `needs.artifacts: true`).

3. **`cosign attest --type spdx`** the image SBOM:

   ```bash
   cosign attest --yes \
     --predicate image-sbom.spdx.json \
     --type spdx \
     "registry.example.com/foo/bar@sha256:..."
   ```

  `image-sbom.spdx.json` is the SPDX SBOM that buildx already
  attached as an unsigned BuildKit attestation manifest on the
  pushed image index; the `docker:` job
   extracts it back into a file (via `docker buildx imagetools inspect --format '{{json .SBOM.SPDX}}'`) and the `cosign-sign:`
   job wraps it in a signed in-toto envelope.

4. **`cosign attest --type slsaprovenance`** the BuildKit provenance:

   ```bash
   cosign attest --yes \
     --predicate image-provenance.json \
     --type slsaprovenance \
     "registry.example.com/foo/bar@sha256:..."
   ```

  Same idea —> buildx attached SLSA `mode=max` provenance as an
  unsigned BuildKit attestation manifest on the pushed image index;
  the `docker:` job extracts it (`--format '{{json.Provenance.SLSA}}'`); the `cosign-sign:` job signs it.

5. **`cosign attest --type openvex`** this project's accepted-risk
   triage document:

   ```bash
   cosign attest --yes \
     --predicate openvex.json \
     --type openvex \
     "registry.example.com/foo/bar@sha256:..."
   ```

   The same file Trivy consumed via `--vex` during the strict scan is
   signed here. Downstream consumers can now verify the triage
   rationale came from this project's CI — *"yes, our scan was clean,
   here's the list of CVEs we explicitly accepted and why"* — without
   trusting a copy of the JSON they pulled from your repo (an attacker
   with repo-write could otherwise rewrite it). See
   [`scanning.md` → The OpenVEX accepted-risk policy](scanning.md#the-openvex-accepted-risk-policy)
   for what the document itself contains.

Each attestation is its own DSSE envelope with its own Fulcio cert
and Rekor entry, they're independent claims and the verifier
checks them independently.

The job ends with a round-trip `cosign verify` + five `cosign verify-
attestation` calls so any misconfigured signature or attestation
trips the pipeline rather than producing a quietly-unverifiable
release.

### What's signed, and what each signature buys you

A released image carries five artifacts rooted at the same image
digest, all cosign-signed:

| Artifact                                  | Predicate source                                            | How to verify                                          |
| ----------------------------------------- | ----------------------------------------------------------- | ------------------------------------------------------ |
| Image manifest                            | `docker buildx` (`docker:` job)                             | `cosign verify` / `make verify-image`                  |
| Vuln-scan attestation                     | `trivy image --format cosign-vuln` (`trivy-image:` job)     | `cosign verify-attestation --type vuln`                |
| SBOM attestation (SPDX)                   | `buildx --sbom=true` → extracted in `docker:`               | `cosign verify-attestation --type spdx`                |
| SLSA provenance attestation (`mode=max`)  | `buildx --provenance=mode=max` → extracted in `docker:`     | `cosign verify-attestation --type slsaprovenance`      |
| OpenVEX accepted-risk attestation         | `openvex.json` at the repo root (checked into repo)         | `cosign verify-attestation --type openvex`             |

**What each artifact actually contains** (so the rest of this
section makes sense):

- **Image manifest** — the image itself. JSON listing every
  filesystem layer + the image config (env vars, CMD, user, workdir).
  The manifest's sha256 *is* the image identity.
- **Vuln-scan claim** — Trivy's output for this specific image at
  scan time: list of CVEs, severities, affected packages, scanner
  version, scan timestamp. A frozen snapshot of *"what was known at
  release time"*, not *"what's known now"*.
- **SBOM (SPDX)** — every package inside the image: OS libs
  (`libc6 2.36`, `openssl 3.0.10`, …), Python packages, license info,
  file hashes. Hundreds of entries for a typical Python+Debian image.
- **SLSA provenance** — the build recipe: git commit + repo URL,
  Dockerfile, base image digests, every package downloaded during the
  build with its hash. Effectively, *"how was this image made?"*.
- **OpenVEX document** — every CVE this project has explicitly
  triaged, the status (`not_affected` / `affected` / `fixed` / `under_
  investigation`), a controlled-vocab justification, and a free-text
  impact statement. Effectively, *"these are the findings we know
  about and our reasoned stance on each"*.

The image manifest *is* the image; the other four are claims
*about* the image, attached in the registry as separate manifests.
In this template, buildx first publishes unsigned BuildKit attestation
manifests on the pushed image index; `cosign-sign:` then publishes
signed OCI referrers for the same logical claims.

**What signing each one buys you specifically:**

| Signed claim                  | Says...                                                                                          | Lets a consumer...                                                                                                                  |
| ----------------------------- | ------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------- |
| Image manifest                | "Bits with digest `@abc` were built by *this project's* CI."                                     | Refuse to run images not built by you. Kubernetes admission controllers gate on this; *the* must-check.                             |
| Vuln-scan attestation         | "Trivy, in this CI job, scanned image `@abc` at time `T` and saw these results."                 | Audit retroactively without trusting CI logs: *"did the release-time scan know about CVE-2026-X?"*. Compliance evidence (SLSA, CRA).|
| SBOM attestation              | "This is the component inventory of image `@abc` at release time."                               | Re-scan past releases against tomorrow's CVE database without re-pulling images. License-compliance reports. *"Using log4j?"*.      |
| SLSA provenance attestation   | "Image `@abc` was built from commit `XYZ` using build config `Z` with these materials."          | Forensics after a breach: was the Dockerfile modified? Did a malicious `RUN curl evil.com` get added? SLSA L3 compliance.           |
| OpenVEX attestation           | "These are the CVEs *this project* has triaged for image `@abc`, with controlled-vocab justifications and impact statements."| Auto-filter scanner noise downstream (Kyverno, admission controllers); see a signed audit trail for procurement / regulator review.|

In general, signing buys you four things — true for every artifact
in the table above:

1. **Authenticity** — the artifact was attached by the named
   identity (not by some attacker with registry-write access).
2. **Integrity** — the bits haven't changed since signing; any
   modification breaks the signature.
3. **Non-repudiation** — Rekor's append-only public log preserves
   the evidence; the signer can't later claim *"I didn't sign that"*.
4. **Identity provenance** *(Sigstore-keyless only)* — the cert
   encodes *who* signed in machine-readable form. Trust is anchored
   at GitLab.com's OIDC issuer, not at a long-lived key file.

Without a signature, an artifact still has *integrity* (the bits in
the registry are what they are), but **no authenticity** — anyone
with registry-write could have placed it there, including an
attacker who compromised the registry.

### Two storage paths: signed cosign referrers + unsigned buildx attestation manifests

After the pipeline runs, the registry contains **two copies** of the
SBOM and **two copies** of the SLSA provenance — same content,
different signing status. This is intentional. Walkthrough:

**Stage 1 — after `docker:` finishes** (`buildx build --sbom=true
--provenance=mode=max --push`):

```text
image @ sha256:abc... (unsigned image)
├─ buildx-attached SBOM (no signature)             ← written by buildx as an index-attached attestation manifest
└─ buildx-attached SLSA provenance (no signature)  ← written by buildx as an index-attached attestation manifest
```

(`trivy-image:` then produces `cosign-vuln.json` as a CI artifact,
not yet in the registry.)

**Stage 2 — after `cosign-sign:` runs:**

```text
image @ sha256:abc...
├─ buildx-attached SBOM (no signature)                       ← UNCHANGED, still there
├─ buildx-attached SLSA provenance (no signature)            ← UNCHANGED, still there
├─ cosign image signature                                     ← NEW (signs the image bits)
├─ cosign --type vuln attestation (signed)                   ← NEW (the Trivy scan)
├─ cosign --type spdx attestation (signed)                   ← NEW, same SBOM content as the buildx one, wrapped in DSSE + signed
├─ cosign --type slsaprovenance attestation (signed)         ← NEW, same provenance content, wrapped in DSSE + signed
└─ cosign --type openvex attestation (signed)                ← NEW (the accepted-risk document)
```

So there really are two SBOMs (identical content; one unsigned, one
signed) and two provenance docs (same). The buildx-unsigned copies
aren't deleted by `cosign-sign:` — they stay in place because they
serve a different audience:

| Audience finds the SBOM via...                              | Reads which copy?                                                                | Cares about the signature? |
| ----------------------------------------------------------- | -------------------------------------------------------------------------------- | -------------------------- |
| `cosign verify-attestation --type spdx`                     | the cosign-signed copy                                                           | Yes                        |
| `docker buildx imagetools inspect`                          | the buildx-unsigned copy                                                         | No                         |
| `oras discover`, `cosign tree`                              | the cosign-signed copy, and the buildx one only if exported in OCI-artifact form | No                         |
| Docker/BuildKit-aware tooling reading raw index manifests   | the buildx-unsigned copy                                                         | No                         |

Cosign-aware consumers get a cryptographic anchor (verifiable
identity, Rekor-logged); Docker/BuildKit-aware tooling can still read
the unsigned build attestations from the image index. The easy mistake
is to treat those unsigned copies as ordinary OCI 1.1 referrers: with
the default BuildKit layout, `oras discover` may not enumerate them
even though `docker buildx imagetools inspect` can read them just fine.
Cosign then adds separately discoverable signed referrers on top of the
same content.

If you ever wanted to consolidate to a single copy: pass
`--sbom=false --provenance=false` to the buildx build and the cosign-
signed attestations become the sole source. Not worth it for the
registry-space saving -> the dual-path discovery is a feature.

### Activation

Zero per-project setup on GitLab.com — `id_tokens` and OIDC are
already wired. For self-hosted GitLab, ensure your instance's OIDC
issuer is reachable from the runner network.

The runner needs network egress to:

- `fulcio.sigstore.dev` — signing CA
- `rekor.sigstore.dev` — transparency log
- `tuf-repo-cdn.sigstore.dev` — root-of-trust updates

That's it. The `cosign-sign:` job runs automatically after every
release on the default branch. See
[*"Using this with private artifacts"*](#using-this-with-private-artifacts)
below for what happens if any of those hosts are unreachable from your
network.

### Replacing cosign

If your organisation mandates [notation](https://notaryproject.dev/)
(Notary v2) or a different signer, swap the `cosign-sign:` job's
image and script. The `docker:` job is unchanged; the build / push /
SBOM / provenance flow doesn't depend on which signer you use.

The attestation steps (`cosign attest --type vuln/spdx/slsaprovenance/openvex`)
don't have direct equivalents in every signer — notation, for
instance, doesn't yet have a stable predicate-attachment story. If
you need both signing portability and signed attestations, two
pragmatic options: keep cosign just for the attestations (it composes
fine with a non-cosign image signature), or attach each predicate as
a sidecar OCI artifact and document the verification flow.

---

## Commit signing: `gitsign`

The release commit produced by `semantic-release` (the
`chore(release): vX.Y.Z` commit) and its accompanying tag are signed
via [gitsign](https://docs.sigstore.dev/cosign/signing/gitsign/) —
the same Sigstore primitives (Fulcio + Rekor) applied to git itself.

Wired up in [`.gitlab/ci/release.yml`](../../.gitlab/ci/release.yml)
when release commit signing is enabled. Gitsign should be installed
only when an actual release is happening — no-release pipeline runs
should skip the install to stay fast.

### Why sign release commits

Without commit signing, anyone with push access can spoof an author
(`git config user.name "Someone Else"`) and the log carries that
author verbatim. The CI then dutifully versions, signs, and releases
the impersonated commit. Signing the release commit closes that gap:
it ties the commit to the CI job's OIDC identity via a Fulcio cert
+ Rekor entry. The whole release chain is now anchored to a single
identity — commit, image, and vuln scan all under the same
`--certificate-identity-regexp`.

### What's signed in this template

**Only release commits and their tags** — produced by
`semantic-release` in CI. We call this *level 3* signing.

Two further levels exist as a future-rollout path:

- **Level 1 — per-developer commit signing.** Every commit, signed
  on the developer's workstation. Requires every contributor to
  install gitsign and configure git locally. Useful as a foundation;
  on its own, it's an honour-system thing.
- **Level 2 — CI verification of dev commits.** Once level 1 is
  universal, add a CI job that rejects any commit whose signature
  doesn't verify against your org's OIDC identity regex. Turns
  level 1 from honour-system into enforced policy.

We ship level 3 because it's the highest-value, lowest-friction step
— releases are the artifact consumers care about, and CI is the one
place where signing setup is centralised. Levels 1+2 are documented
in [Future expansion — levels 1 and 2](#future-expansion-levels-1-and-2)
below for when the contributor base is ready.

### Mechanics

Identical to cosign keyless signing, just applied to git instead of
an image manifest:

1. GitLab issues a short-lived OIDC token via the same `id_tokens:`
   pattern already used by cosign (`SIGSTORE_ID_TOKEN: aud: sigstore`).
2. Gitsign exchanges the token at Fulcio for an ephemeral x509 cert
   (~10 min lifetime), in the OpenPGP wire format git natively
   understands.
3. The cert signs the release commit and tag.
4. The signing event lands in Rekor.
5. The ephemeral private key is destroyed.

Tool versions:

- `GITSIGN_VERSION` is pinned in `.gitlab/ci/release.yml`, tracked by
  Renovate's custom manager (same `# renovate: datasource=...`
  pattern used for `COSIGN_VERSION`).
- Installed only when an actual release is happening so no-release
  pipeline runs stay fast.

### Hardware-backed identity: YubiKey, WebAuthn

Gitsign is **keyless** by design — there's no long-lived signing key
to put on a hardware token. The way to combine it with a YubiKey is
at the **OIDC layer**: configure your IdP (Google, GitLab, GitHub,
Okta, Entra) to require **WebAuthn / FIDO2 / passkey** authentication
for the relevant accounts. Every gitsign signature is then anchored
in a physical hardware tap *at sign-in time*, while the signing key
itself remains ephemeral and is destroyed after each commit.

For the **level 3** (CI) case in this template, the relevant
"sign-in" is GitLab issuing the CI job's OIDC token — that happens
automatically without human interaction, so WebAuthn doesn't apply
here. WebAuthn becomes relevant if and when you roll out level 1
(developer commits), at which point each developer signing locally
will see a browser-based OIDC login on first use of gitsign per
shell session.

### Future expansion: levels 1 and 2

This template currently implements only **level 3** (CI release
commits). Two further levels are documented here for future rollout
when the contributor base is ready:

**Level 1 — per-developer commit signing.** Each developer installs
gitsign locally and signs their own commits. Setup:

1. Install gitsign — see the
   [Sigstore docs](https://docs.sigstore.dev/cosign/signing/gitsign/)
   for the latest binary.
2. Configure git globally:

   ```bash
   git config --global gpg.x509.program gitsign
   git config --global gpg.format       x509
   git config --global commit.gpgsign   true
   git config --global tag.gpgsign      true
   ```

3. The first commit per shell session opens a browser for OIDC
   login; the cert is then cached for that session.

Pair with WebAuthn-enforced OIDC on the IdP for hardware assurance.

**Level 2 — CI verification of dev commits.** Once level 1 is
universal on the team, add a CI job that runs:

```bash
gitsign verify \
  --certificate-identity-regexp "<your-org-regex>" \
  --certificate-oidc-issuer    "<your-idp>" \
  <commit>
```

on every commit in an MR. Reject unsigned or wrongly-signed commits
before merge.

Level 2 only makes sense **after** level 1 is fully rolled out.
Otherwise it becomes a constant CI failure source and the team will
ask you to disable it.

### Replacing gitsign

Two pragmatic alternatives:

- **SSH commit signing with FIDO2 keys.** `git config gpg.format ssh`
  + `commit.gpgsign true` plus a `ssh-ed25519-sk` / `ecdsa-sk` key on
  a YubiKey. Simpler, no Sigstore dependency, no OIDC plumbing —
  but no transparency log, no project-scoped identity, and
  verification is harder (you have to distribute the public-key
  allowlist out-of-band).
- **Classic GPG with hardware-held key.** Works, well-trodden, but
  the key-management story is the same as for key-based image
  signing: long-lived secret, rotation pain, no transparency. Hard
  to justify in 2026.

---

## Verification

### Quick reference

You have six independent signed claims to check. All six use the
**same identity regex + OIDC issuer**, so an admission controller can
reuse one trust policy across them.

```bash
IDENTITY="^https://gitlab.com/<your-group>/<your-project>//"
ISSUER="https://gitlab.com"
IMG="registry.gitlab.com/<your-group>/<your-project>@sha256:..."
TAG="v1.2.3"

# 1. Image manifest
cosign verify \
  --certificate-identity-regexp "$IDENTITY" \
  --certificate-oidc-issuer    "$ISSUER" \
  "$IMG"

# 2. Vuln-scan attestation
cosign verify-attestation --type vuln \
  --certificate-identity-regexp "$IDENTITY" \
  --certificate-oidc-issuer    "$ISSUER" \
  "$IMG"

# 3. SBOM attestation (SPDX)
cosign verify-attestation --type spdx \
  --certificate-identity-regexp "$IDENTITY" \
  --certificate-oidc-issuer    "$ISSUER" \
  "$IMG"

# 4. SLSA provenance attestation
cosign verify-attestation --type slsaprovenance \
  --certificate-identity-regexp "$IDENTITY" \
  --certificate-oidc-issuer    "$ISSUER" \
  "$IMG"

# 5. OpenVEX accepted-risk attestation
cosign verify-attestation --type openvex \
  --certificate-identity-regexp "$IDENTITY" \
  --certificate-oidc-issuer    "$ISSUER" \
  "$IMG"

# 6. Release commit / tag
gitsign verify \
  --certificate-identity-regexp "$IDENTITY" \
  --certificate-oidc-issuer    "$ISSUER" \
  "$TAG"
```

If any of the six fails, treat the release as untrusted. In practice
the image-manifest signature + the commit signature are the
must-check ones; the four attestations are post-release auditing
(`"what was in this build?"`, `"how was it built?"`, `"was it clean
at release time?"`, `"what did we triage and why?"`). Admission
controllers typically gate on (1) alone, since failing the others
doesn't mean the image is malicious — just that some specific
attestation didn't make it.

### Image verification: `make verify-image`

Implemented in [`scripts/verify_image.py`](../../scripts/verify_image.py).
The script reads the platform (gitlab / github) and host from
`[tool.semantic_release.remote]` in
[`pyproject.toml`](../../pyproject.toml). There is exactly one source
of truth for *"what platform are we on"* — flipping
`type = "gitlab"` to `type = "github"` (and swapping the CI signing
job) updates the verifier with no edits anywhere else.

Locally:

```bash
make verify-image IMAGE=registry.gitlab.com/myorg/myproject@sha256:abc...
```

The Make target defaults to a **host-anchored** cert identity (*"must
be signed by something on this GitLab/GitHub host"*) — fine for
ad-hoc developer checks. For automated deploy gates where you want
to enforce *"signed by **this specific project's** CI"*, invoke the
script directly with `--project`:

```bash
python scripts/verify_image.py \
  --project myorg/myproject \
  registry.gitlab.com/myorg/myproject@sha256:abc...
```

### In admission controllers / GitOps / Kubernetes

For consumers without Python — Kubernetes admission controllers,
GitOps agents, Notation / Connaisseur / Kyverno policies — invoke
`cosign verify` directly with the same flags. The script logs the
exact regex + issuer it constructs on each run, so you can copy
them verbatim from a successful local verify into your admission
policy.

### Inspecting the vuln-attestation payload

`cosign verify-attestation` returns the full DSSE envelope. To pull
out the readable Trivy predicate (scanner version, scan timestamp,
list of findings per package):

```bash
cosign verify-attestation \
  --type vuln \
  --certificate-identity-regexp "$IDENTITY" \
  --certificate-oidc-issuer    "$ISSUER" \
  "$IMG" \
  | jq '.payload | @base64d | fromjson | .predicate'
```

### Why pin to a digest, not a tag

`registry.example.com/foo/bar:v1.2.3` can be re-pushed (the tag is
mutable); `registry.example.com/foo/bar@sha256:...` cannot (the
digest *is* the content). Always pin to the digest in production
verification — `make verify-image` will refuse to run against a tag.

The release pipeline emits the digest in three places to make this
easy: the `image:` CI artifact (`image.env`), the GitLab release
notes, and the `cosign-vuln.json` predicate. Pick whichever is
convenient.

---

## Using this with private artifacts

A common worry, especially for internal / proprietary projects:

> *"Sigstore's Fulcio and Rekor are public. Doesn't that leak my
> closed-source code, my CVE list, or my release schedule?"*

Short answer: **no, but it does leak some metadata.** Whether that
matters depends on your threat model. The default (public Sigstore)
is right for the overwhelming majority of cases — including most
internal-only projects — but two alternatives exist if it isn't.

### What Rekor records (and what stays private)

Rekor is an **append-only public log of signing events**. Each
event the template produces (one for the image manifest, one for the
vuln attestation, one for the release commit + tag) writes one
Rekor entry. Each entry contains:

| Rekor entry contains                                       | Rekor entry does **not** contain                          |
| ---------------------------------------------------------- | --------------------------------------------------------- |
| The hash of what was signed (image digest, commit hash, attestation payload hash) | The signed bits themselves                                |
| The Fulcio cert, which encodes the OIDC identity (e.g. `https://gitlab.com/myorg/myproject//.gitlab-ci.yml@refs/heads/main`) | The OIDC token, or any other identity claim than what Fulcio chose to embed |
| A trusted timestamp                                        | Source code, layer contents, CVE list, package names, environment variables |
| The detached signature                                     | The private key (it was destroyed)                        |

What this means concretely for an internal/private project:

- **Image bits stay private.** They live in your registry. Rekor
  only has their hash.
- **CVE findings stay private.** The vuln attestation predicate
  lives at the registry (`cosign-vuln.json` is uploaded as an OCI
  artifact, not to Rekor). Rekor only has the predicate's hash.
- **Source code stays private.** Same as the image — it lives in
  your forge. Rekor only ever sees the release-commit hash.
- **What leaks** is the metadata: *"the OIDC identity at
  `gitlab.com/myorg/myproject` produced a signed artifact with hash
  `sha256:abc...` at timestamp `T`."*

That metadata leak is often acceptable even for closed-source
products — it's the kind of thing an attacker could mostly infer
from public release pages or container registries anyway. But for
some threat models (highly sensitive customer projects, classified
work, projects where even the release *cadence* is sensitive), it
isn't. The alternatives below address that case.

### Option A: keep public Sigstore (recommended default)

No changes. The metadata leak is bounded (project name + identity +
timestamps + hashes), the public Rekor log gives you free third-
party timestamping and append-only auditability, and the
infrastructure cost is zero. This is what
[Kubernetes](https://kubernetes.io/), [npm](https://docs.npmjs.com/generating-provenance-statements),
[PyPI](https://blog.pypi.org/posts/2024-11-14-pypi-now-supports-digital-attestations/),
and most large open-source ecosystems use, including for plenty of
closed-source artifacts (it's the *publishing* that needs to be
public, not the *signed thing*).

### Option B: self-host Sigstore

Run your own Fulcio + Rekor + TUF root inside your network. Your
signatures and transparency log never touch the public internet, and
the OIDC issuer can be your internal IdP rather than a public one.

The cosign and gitsign clients accept private endpoints via env vars
/ flags — no source changes needed:

```yaml
# .gitlab/ci/sign.yml — add to the cosign-sign: job's `variables:`
variables:
  COSIGN_FULCIO_URL: "https://fulcio.internal.example.com"
  COSIGN_REKOR_URL:  "https://rekor.internal.example.com"
  COSIGN_OIDC_ISSUER: "https://gitlab.internal.example.com"
  TUF_ROOT:          "/etc/sigstore/root.json"   # your private root of trust
```

```yaml
# .gitlab/ci/release.yml — add to the semantic-release: job's `variables:`
variables:
  GITSIGN_FULCIO_URL: "https://fulcio.internal.example.com"
  GITSIGN_REKOR_URL:  "https://rekor.internal.example.com"
  GITSIGN_OIDC_ISSUER: "https://gitlab.internal.example.com"
```

Operational cost: someone has to run Fulcio + Rekor (Kubernetes
manifests are available upstream, but it's still a service to
maintain), and consumers have to be configured with your private
TUF root. For organisations already running their own PKI or
certificate transparency log, this is a small incremental ask; for
a five-person team, it's overkill.

When to choose B:

- Even the existence / cadence / project-name metadata is sensitive
  (defence, classified work).
- Regulatory regime requires that no signing metadata leaves your
  network (some EU sovereignty regimes, some intelligence-community
  rules).
- You already operate the infrastructure (a private Sigstore stack
  is roughly the same shape as a private CA + transparency log,
  which you may already have).

### Option C: drop keyless, use key-based signing

If running Sigstore at all (public or private) isn't acceptable —
e.g. air-gapped builds, or you want the absolute minimum dependency
surface — fall back to cosign **key-based** signing:

```yaml
# .gitlab/ci/sign.yml — replace the cosign sign / attest steps
script:
  - cosign sign   --key "$COSIGN_PRIVATE_KEY" --tlog-upload=false "$IMAGE_REF"
  - cosign attest --key "$COSIGN_PRIVATE_KEY" --tlog-upload=false \
                  --predicate cosign-vuln.json --type vuln "$IMAGE_REF"
```

You now own a long-lived `COSIGN_PRIVATE_KEY` (store as a protected,
masked CI variable; ideally back it with an HSM via `cosign generate-
key-pair --kms ...`). Consumers verify with `--key cosign.pub`
instead of identity flags. No Rekor entry, no Fulcio cert, no OIDC
identity baked in.

What you lose:

- **Identity in the signature.** The signature says "someone with
  this key signed this", not "this CI job, in this project, on this
  date, signed this". You have to bolt provenance on out-of-band.
- **Transparency.** No append-only log. A compromised key could
  silently re-sign artifacts and you'd have no way to detect the
  divergence.
- **Painless rotation.** You're back to key-management ceremony for
  every rotation.

What you keep:

- Air-gap compatibility.
- A single, well-understood, well-tested workflow (cosign supports
  both modes equally).
- The vuln-attestation flow (just with `--key` and `--tlog-upload=
  false`).

When to choose C:

- Truly air-gapped CI.
- Regulatory regime that mandates a specific key-storage standard
  (FIPS 140-2 level 3 HSM in a controlled facility, etc.) and
  treats ephemeral keys as non-compliant.
- You have battle-tested key-management infrastructure and the cost
  of adopting it for signing is dominated by what you already pay.

### Choosing

| Project shape                                                        | Recommended option |
| -------------------------------------------------------------------- | ------------------ |
| Public open-source                                                   | A (public Sigstore)|
| Private/internal SaaS, normal enterprise                             | A (public Sigstore)|
| Closed-source product where metadata leak is mildly uncomfortable    | A — re-read the table above and check if it's actually a problem |
| Classified / sovereign / regulated where metadata cannot leave net   | B (self-hosted)    |
| Air-gapped CI                                                        | C (key-based)      |
| "We have an HSM and a compliance regime that requires it"            | C (key-based)      |

The default in this template is **A** because it's the only option
that requires zero infrastructure to operate and the only one that
gives you a public, free, third-party audit trail. Don't move off
it without a concrete reason — "Rekor is public" by itself isn't one;
"my legal department says no project-name metadata can leave our
network" is.

---

## Replacing Sigstore

To remove Sigstore signing entirely (you accept unsigned releases):

1. Delete [`.gitlab/ci/sign.yml`](../../.gitlab/ci/sign.yml).
2. Remove the `id_tokens:` block and `GITSIGN_VERSION` from
   [`.gitlab/ci/release.yml`](../../.gitlab/ci/release.yml).
3. Remove any `install_gitsign` / `configure_git_signing` calls from
  [`.gitlab/ci/release.yml`](../../.gitlab/ci/release.yml).
4. Delete [`scripts/verify_image.py`](../../scripts/verify_image.py)
   and the `verify-image` target in [`Makefile`](../../Makefile).
5. Drop the `sign` stage from `.gitlab/ci/base.yml`.

You'll then publish images that no one — including you — can verify.
That's fine for prototypes or internal-tools-only projects, but
think carefully before doing it on anything that ships to other
people.

To replace Sigstore with a different signer: see
[*Replacing cosign*](#replacing-cosign) and
[*Replacing gitsign*](#replacing-gitsign) above.
