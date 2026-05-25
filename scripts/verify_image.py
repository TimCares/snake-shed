"""Verify a Sigstore cosign signature against the configured remote.

Reads ``[tool.semantic_release.remote]`` from ``pyproject.toml`` to determine
the signing platform (``gitlab`` or ``github``) and its host, then builds the
matching ``--certificate-oidc-issuer`` and ``--certificate-identity-regexp``
for ``cosign verify``. Keeping verification config paired with the existing
remote config means flipping ``type = "gitlab"`` to ``type = "github"`` (and
swapping the signing job) updates the verifier with no edits here.

Usage::

    python scripts/verify_image.py <IMAGE_REF> [--project <group/repo>]

* ``IMAGE_REF`` is a full image reference, e.g.
  ``registry.gitlab.com/myorg/myproject@sha256:abc…``. Pin to a ``@sha256:``
  digest for production verification — tags can be re-pushed, digests cannot.
* ``--project`` anchors the certificate-identity regex to a specific
  ``<group>/<repo>`` path. Recommended for automated deploy gates;
  optional for ad-hoc developer checks.

Uses ``cosign`` from ``PATH`` if available; otherwise falls back to running
``ghcr.io/sigstore/cosign/cosign:latest`` via Docker. Exit code mirrors
``cosign verify``: 0 on success, non-zero on any failure.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

PYPROJECT = Path("pyproject.toml")
COSIGN_IMAGE = "ghcr.io/sigstore/cosign/cosign:latest"

_GITHUB_OIDC_ISSUER = "https://token.actions.githubusercontent.com"
_DEFAULT_DOMAINS: dict[str, str] = {
    "gitlab": "gitlab.com",
    "github": "github.com",
}


def _load_remote_config() -> tuple[str, str]:
    """Return ``(remote_type, domain)`` from ``pyproject.toml``.

    Falls back to ``("gitlab", "gitlab.com")`` if the file or the
    ``[tool.semantic_release.remote]`` block is missing — matching the
    template's shipped default.

    Returns:
        A 2-tuple of the platform string and the host string.

    Raises:
        ValueError: when ``type`` is set to anything other than the supported
            ``gitlab`` / ``github`` values.
    """
    if not PYPROJECT.exists():
        return ("gitlab", "gitlab.com")

    with PYPROJECT.open("rb") as f:
        data = tomllib.load(f)

    remote = data.get("tool", {}).get("semantic_release", {}).get("remote", {})
    remote_type = remote.get("type", "gitlab")
    if remote_type not in _DEFAULT_DOMAINS:
        msg = (
            f"[tool.semantic_release.remote].type = {remote_type!r} is not "
            f"supported; expected one of {sorted(_DEFAULT_DOMAINS)}"
        )
        raise ValueError(msg)
    domain = remote.get("domain") or _DEFAULT_DOMAINS[remote_type]
    return (remote_type, domain)


def _build_identity_args(remote_type: str, domain: str, project: str | None) -> tuple[str, str]:
    """Return ``(certificate_identity_regexp, oidc_issuer)`` for the platform.

    Args:
        remote_type: ``gitlab`` or ``github``.
        domain: Host name from ``pyproject.toml`` (or default per platform).
        project: Optional ``<group>/<repo>`` path; when provided, the
            certificate-identity regex is anchored to exactly that project
            rather than any project on the host.

    Returns:
        A 2-tuple ``(regex, issuer)`` ready for ``cosign verify``.
    """
    project_anchor = re.escape(project) if project else r".+?"

    if remote_type == "gitlab":
        # Cert subject format:
        #   https://<host>/<group>/<project>//<ci-file>@<ref>
        return (
            rf"^https://{re.escape(domain)}/{project_anchor}//",
            f"https://{domain}",
        )

    # GitHub Actions cert subject format:
    #   https://github.com/<owner>/<repo>/.github/workflows/<wf>@<ref>
    return (
        rf"^https://{re.escape(domain)}/{project_anchor}/\.github/workflows/",
        _GITHUB_OIDC_ISSUER,
    )


def _find_cosign_runner() -> list[str] | None:
    """Locate a way to invoke ``cosign``.

    Prefers a locally-installed ``cosign`` binary; falls back to running the
    official cosign image via ``docker``.

    Returns:
        The argv prefix that should be followed by ``verify ...`` arguments,
        or ``None`` if neither cosign nor docker is on ``PATH``.
    """
    local = shutil.which("cosign")
    if local:
        return [local]
    docker = shutil.which("docker")
    if docker:
        return [docker, "run", "--rm", COSIGN_IMAGE]
    return None


def main() -> int:
    """Parse args, load config, and run ``cosign verify``.

    Returns:
        The exit code of the underlying ``cosign verify`` invocation, or
        ``2`` on config errors / ``127`` when no cosign runner is available.
    """
    parser = argparse.ArgumentParser(
        description="Verify a cosign signature against the configured remote."
    )
    parser.add_argument(
        "image",
        help=("Image reference, e.g. registry.gitlab.com/group/project@sha256:abc..."),
    )
    parser.add_argument(
        "--project",
        help=(
            "Anchor the cert-identity regex to <group>/<repo>. Recommended "
            "for automated deploy gates; optional for ad-hoc checks."
        ),
    )
    args = parser.parse_args()

    try:
        remote_type, domain = _load_remote_config()
    except ValueError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2

    runner = _find_cosign_runner()
    if runner is None:
        sys.stderr.write(
            "error: neither `cosign` nor `docker` is on PATH; install one of them "
            "to run image verification.\n"
        )
        return 127

    identity_re, issuer = _build_identity_args(remote_type, domain, args.project)
    cmd = [
        *runner,
        "verify",
        "--certificate-identity-regexp",
        identity_re,
        "--certificate-oidc-issuer",
        issuer,
        args.image,
    ]

    scope = f"{args.project!s} on {domain}" if args.project else f"any project on {domain}"
    sys.stderr.write(
        f"Verifying {args.image}\n"
        f"  platform: {remote_type}\n"
        f"  scope:    {scope}\n"
        f"  issuer:   {issuer}\n"
    )
    return subprocess.run(cmd, check=False).returncode  # noqa: S603


if __name__ == "__main__":
    raise SystemExit(main())
