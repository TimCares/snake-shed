# ruff: noqa: T201 -> allow print
"""Build this project's Docker image locally and scan it with Trivy.

Local counterpart of the CI `trivy-image:` job. Builds from the repo
`Dockerfile`, tags the result with a project-local name, then runs Trivy
with `openvex.json` when present (same accepted-risk policy CI applies to
release images). A missing VEX file means no CVE suppressions — matching
`check_vex.py` and `py_audit_ignores_from_vex.py`.

Usage::

    python scripts/trivy_image_local.py

Requires a Docker daemon (`docker build` and `docker run`). The scan
container mounts `/var/run/docker.sock` so Trivy can inspect the locally
built image without pushing it anywhere.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DOCKERFILE = REPO_ROOT / "docker" / "Dockerfile"
VEX_FILE = REPO_ROOT / "openvex.json"
TRIVY_IMAGE = "ghcr.io/aquasecurity/trivy:latest"


def _project_scan_tag() -> str:
    """Return a local-only image ref derived from `[project].name`."""
    pyproject = REPO_ROOT / "pyproject.toml"
    name = "project"
    if pyproject.exists():
        with pyproject.open("rb") as f:
            name = tomllib.load(f).get("project", {}).get("name", name)
    safe = re.sub(r"[^a-z0-9._-]", "-", str(name).lower()).strip("-") or "project"
    return f"{safe}-trivy-scan:local"


def _run(cmd: list[str], *, cwd: Path | None = None) -> int:
    """Run *cmd*, streaming output; return the process exit code."""
    result = subprocess.run(cmd, cwd=cwd, check=False)  # noqa: S603
    return result.returncode


def main(argv: list[str] | None = None) -> int:
    """Build the project image and scan it with Trivy + OpenVEX."""
    parser = argparse.ArgumentParser(
        description="Build this project's Docker image and scan it with Trivy."
    )
    parser.add_argument(
        "--dockerfile",
        type=Path,
        default=DEFAULT_DOCKERFILE,
        help=f"Dockerfile to build (default: {DEFAULT_DOCKERFILE.relative_to(REPO_ROOT)})",
    )
    parser.add_argument(
        "--context",
        type=Path,
        default=REPO_ROOT,
        help="Build context directory (default: repository root)",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Pass --no-cache to docker build",
    )
    args = parser.parse_args(argv)

    if not shutil.which("docker"):
        print("docker not found in PATH", file=sys.stderr)
        return 1

    if not args.dockerfile.is_file():
        print(f"Dockerfile not found: {args.dockerfile}", file=sys.stderr)
        return 1

    image_ref = _project_scan_tag()
    build_cmd = [
        "docker",
        "build",
        "-t",
        image_ref,
        "-f",
        str(args.dockerfile.resolve()),
        str(args.context.resolve()),
    ]
    if args.no_cache:
        build_cmd.insert(2, "--no-cache")

    print(f"Building {image_ref} ...", file=sys.stderr)
    if _run(build_cmd, cwd=REPO_ROOT) != 0:
        return 1

    print(f"Scanning {image_ref} with Trivy ...", file=sys.stderr)
    trivy_cmd = ["docker", "run", "--rm"]
    if VEX_FILE.exists():
        trivy_cmd.extend(["-v", f"{REPO_ROOT}:/repo:ro"])
    trivy_cmd.extend(
        [
            "-v",
            "/var/run/docker.sock:/var/run/docker.sock",
            TRIVY_IMAGE,
            "image",
            "--severity",
            "HIGH,CRITICAL",
            "--exit-code",
            "1",
        ]
    )
    if VEX_FILE.exists():
        trivy_cmd.extend(["--vex", f"/repo/{VEX_FILE.name}"])
    trivy_cmd.append(image_ref)
    return _run(trivy_cmd, cwd=REPO_ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
