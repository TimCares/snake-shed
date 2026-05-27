# OpenVEX downstream: from this repo to your governance platform

The [`openvex.json`](../../openvex.json) at the repo root is the
**engineer-facing source of truth** for accepted-risk CVE triage. It is
not, by itself, the governance system, governance happens when this
document is consumed by the org's vulnerability-management stack.
This page describes how that consumption works.

## Format universality

Every mainstream vulnerability-management tool either consumes OpenVEX
natively or accepts a [`vexctl`](https://github.com/openvex/vexctl)-
converted CycloneDX VEX / CSAF VEX equivalent. The translation is
**semantically faithful**, the triage decision (which CVE, which
product, which status, the justification's intent) survives in every
direction, but not strictly bit-lossless, since each format carries
metadata the others don't.

## Consumer landscape

| Consumer type             | Example tools                                                                                          | Reads OpenVEX                        |
| ------------------------- | ------------------------------------------------------------------------------------------------------ | ------------------------------------ |
| Direct scanner            | Trivy, Grype, Anchore Engine, JFrog Xray                                                               | Native                               |
| Aggregator / hub          | [DependencyTrack](https://dependencytrack.org/), [GUAC](https://guac.sh/) (OpenSSF), Trivy hosted VEX repo | Native                               |
| Enterprise SCA platform   | Sonatype IQ, Mend, Snyk, Black Duck                                                                    | Direct or via `vexctl` conversion    |
| Compliance export         | SOC 2 / FedRAMP / EU CRA evidence packages                                                             | `vexctl` → CSAF VEX                  |

## End-to-end flow

```text
openvex.json (repo) ──► PR review ──► cosign attest ──► Registry ──► Org governance platform
                       (CODEOWNERS)   --type openvex     + Rekor      (pulls signed attestation,
                                                                       aggregates across projects,
                                                                       enforces org-level policy)
```

The template owns the first four steps (authoring, review, signing,
publication). The fifth — org-wide aggregation, dashboards, policy
enforcement, compliance reporting — is the adopter's responsibility,
since it depends on the org's existing tooling.

## Pulling the signed attestation

```bash
cosign verify-attestation \
  --certificate-identity-regexp '<your-CI-identity-regex>' \
  --certificate-oidc-issuer-regexp '<your-OIDC-issuer>' \
  --type openvex \
  <image>@sha256:<digest> \
  | jq -r '.payload | @base64d | fromjson | .predicate' \
  > openvex.from-attestation.json
```

The extracted payload is what an aggregator (GUAC, DependencyTrack,
Sonatype IQ, ...) ingests. The authoring-side enforcement story (the
`vex-schema` and `vex-freshness` pre-commit hooks) lives in
[`scanning.md`](scanning.md#the-openvex-accepted-risk-policy).
