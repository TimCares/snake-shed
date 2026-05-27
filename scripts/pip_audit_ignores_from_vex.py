"""Translate the OpenVEX document into ``pip-audit --ignore-vuln`` flags.

Why this script exists
----------------------
This repo uses an OpenVEX document (`openvex.json` at the repo root) as
the single source of truth for accepted-risk CVEs across all scanners.
Trivy consumes OpenVEX natively via ``--vex <path>``. ``pip-audit`` does
**not** yet support VEX (see https://github.com/pypa/pip-audit/issues/231)
and only accepts ``--ignore-vuln <ID>`` CLI flags.

This script reads the VEX file and prints a single
space-separated line of ``--ignore-vuln <ID>`` flags for every statement
whose status filters the vuln out (``not_affected`` or ``fixed``).

Usage
-----
Invoked from the ``Makefile``::

    PIP_AUDIT_IGNORES := $(shell python3 scripts/pip_audit_ignores_from_vex.py)
    pip-audit $(PIP_AUDIT_IGNORES)

Exit code 0 on success. Exit code 1 on malformed JSON or
unreadable file.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

VEX_FILE = Path("openvex.json")

FILTERING_STATUSES = {"not_affected", "fixed"}


def _ids_from_statement(stmt: dict[str, Any]) -> list[str]:
    """Return every CVE/GHSA/PYSEC identifier carried by a statement."""
    vuln = stmt.get("vulnerability") or {}
    name = vuln.get("name")
    aliases = vuln.get("aliases") or []
    return [v for v in [name, *aliases] if isinstance(v, str) and v]


def main() -> int:
    """Print ``--ignore-vuln <ID>`` flags for every filterable VEX statement."""
    if not VEX_FILE.exists():
        return 0

    try:
        doc = json.loads(VEX_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"{VEX_FILE}: cannot read VEX document ({exc})\n")
        return 1

    statements = doc.get("statements") if isinstance(doc, dict) else None
    if not isinstance(statements, list):
        return 0

    flags: list[str] = []
    seen: set[str] = set()
    for stmt in statements:
        if not isinstance(stmt, dict):
            continue
        if stmt.get("status") not in FILTERING_STATUSES:
            continue
        for vid in _ids_from_statement(stmt):
            if vid in seen:
                continue
            seen.add(vid)
            flags.extend(("--ignore-vuln", vid))

    if flags:
        sys.stdout.write(" ".join(flags))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
