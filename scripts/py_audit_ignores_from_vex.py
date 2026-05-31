"""Translate the OpenVEX document into ``uv audit --ignore`` flags.

Why this script exists
----------------------
This repo uses an OpenVEX document (`openvex.json` at the repo root) as
the single source of truth for accepted-risk CVEs across all scanners.
Trivy consumes OpenVEX natively via ``--vex <path>``. ``uv`` does
**not** yet support VEX
and only accepts per-ID ``--ignore <ID>`` CLI flags.

This script reads the VEX file and prints a single
space-separated line of ``--ignore <ID>`` flags for every statement
whose status filters the vuln out (``not_affected`` or ``fixed``).
Those are product-impact statements, so they map to unconditional ignores;
``--ignore-until-fixed`` would incorrectly re-open findings based on advisory
fix availability instead.

Only one preferred ID is emitted per statement. ``uv audit`` already matches
advisory aliases, so expanding every alias into its own ``--ignore`` flag only
creates redundant "does not match" warnings once the first alias suppresses the
finding.

Usage
-----
Invoked from the ``Makefile``::

    PY_AUDIT_IGNORES := $(shell uv run python scripts/py_audit_ignores_from_vex.py)
    uv audit $(PY_AUDIT_IGNORES)

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
_ID_PREFIX_PREFERENCE = ("PYSEC-", "GHSA-", "CVE-")


def _ids_from_statement(stmt: dict[str, Any]) -> list[str]:
    """Return unique advisory identifiers for a PyPI statement in stable order."""
    includes_pypi = any(
        "pkg:pypi" in product.get("@id", "") for product in stmt.get("products", [])
    )
    if not includes_pypi:
        return []

    vuln = stmt.get("vulnerability", {})
    name = vuln.get("name")
    aliases = vuln.get("aliases", [])
    ids: list[str] = []
    seen: set[str] = set()
    for value in [name, *aliases]:
        if not isinstance(value, str) or not value or value in seen:
            continue
        seen.add(value)
        ids.append(value)
    return ids


def _preferred_id(ids: list[str]) -> str | None:
    """Pick one ID that best matches uv audit's Python advisory vocabulary."""
    for prefix in _ID_PREFIX_PREFERENCE:
        for value in ids:
            if value.startswith(prefix):
                return value
    return ids[0] if ids else None


def main() -> int:
    """Print ``--ignore <ID>`` flags for every filterable VEX statement."""
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
        ids = _ids_from_statement(stmt)
        if not ids or any(value in seen for value in ids):
            continue

        preferred_id = _preferred_id(ids)
        if preferred_id is None:
            continue

        seen.update(ids)
        flags.extend(("--ignore", preferred_id))

    if flags:
        sys.stdout.write(" ".join(flags))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
