"""Enforce LOCAL policy on the OpenVEX document.

Structural validation (required fields, enums, conditional requirements,
`format` constraints, `additionalProperties: false`, …) is delegated to
the upstream OpenVEX JSON Schema, fetched live from
``https://raw.githubusercontent.com/openvex/spec/main/openvex_json_schema.json``
by the ``check-jsonschema`` pre-commit hook (alias ``vex-schema``).
This script only enforces what JSON Schema *cannot* express:

1. **Freshness.** Every statement's ``last_updated`` timestamp (or the
   document-level ``timestamp`` fallback) was bumped within the last
   ``MAX_AGE_DAYS`` days. This is the local-policy analogue of the old
   ``.trivyignore`` ``exp:YYYY-MM-DD`` suffix — instead of a forward
   expiry, the window is computed at check time from when the statement
   was last re-triaged.

2. **Stricter ``not_affected`` rule.** A ``status: not_affected``
   statement MUST carry BOTH a controlled-vocab ``justification`` AND a
   free-text ``impact_statement``. The OpenVEX spec requires only one
   of the two; the stricter rule here keeps the project-specific
   context (the ``impact_statement``) from being silently dropped
   behind a rubber-stamp controlled-vocab value, which is exactly what
   the old ``.trivyignore`` justification policy was designed to
   prevent.

Exit code 0 means the local policy is satisfied (or the VEX file is
absent, empty suppression means no suppression). Exit code 1 means at least one
violation; diagnostics go to stderr with ``path:json-pointer`` prefixes
so editors and CI can navigate.

Invoked by the ``vex-freshness`` pre-commit hook and ``make vex-check``
(which also runs ``vex-schema`` for the structural half). Pure stdlib
— no project deps.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

VEX_FILE = Path("openvex.json")
MAX_AGE_DAYS = 180


def _parse_ts(value: object) -> dt.datetime | None:
    """Parse an ISO 8601 timestamp string, accepting the ``Z`` UTC suffix."""
    if not isinstance(value, str):
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _check_freshness(
    stmt: dict[str, Any],
    idx: int,
    doc_ts: dt.datetime | None,
    now: dt.datetime,
    errors: list[str],
) -> None:
    """Append a diagnostic if the statement has no fresh ``last_updated``."""
    raw = stmt.get("last_updated") or stmt.get("timestamp")
    stmt_ts = _parse_ts(raw) if raw is not None else doc_ts
    if stmt_ts is None:
        errors.append(
            f"{VEX_FILE}:/statements/{idx}/last_updated: missing — "
            f"add an ISO 8601 timestamp recording the last re-triage"
        )
        return

    age = now - stmt_ts
    if age > dt.timedelta(days=MAX_AGE_DAYS):
        deadline = stmt_ts + dt.timedelta(days=MAX_AGE_DAYS)
        errors.append(
            f"{VEX_FILE}:/statements/{idx}/last_updated: "
            f"statement is {age.days} days old (max {MAX_AGE_DAYS}, "
            f"expired on {deadline.date().isoformat()}) — re-triage and "
            f"bump `last_updated` to today, or remove the statement"
        )


def _check_impact_statement(stmt: dict[str, Any], idx: int, errors: list[str]) -> None:
    """Enforce the stricter local rule: ``not_affected`` needs an ``impact_statement``.

    The OpenVEX spec allows ``justification`` OR ``impact_statement``
    for ``not_affected``; this project requires BOTH so the
    project-specific reasoning (the ``impact_statement``) can't be
    silently dropped behind the controlled-vocab value.
    """
    if stmt.get("status") != "not_affected":
        return
    if not stmt.get("impact_statement"):
        errors.append(
            f"{VEX_FILE}:/statements/{idx}/impact_statement: "
            f"local policy requires `not_affected` statements to carry "
            f"a free-text `impact_statement` describing what makes the "
            f"CVE non-applicable HERE (the controlled-vocab "
            f"`justification` alone is not enough)"
        )


def main() -> int:
    """Validate the OpenVEX document against the LOCAL policy.

    Structural validation is delegated to ``check-jsonschema`` against
    the upstream schema URL; here we only check freshness and the
    stricter local ``not_affected`` rule.
    """
    if not VEX_FILE.exists():
        return 0

    try:
        doc = json.loads(VEX_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return 0

    if not isinstance(doc, dict):
        return 0

    statements = doc.get("statements")
    if not isinstance(statements, list):
        return 0

    doc_ts = _parse_ts(doc.get("timestamp"))
    now = dt.datetime.now(tz=dt.UTC)
    errors: list[str] = []

    for idx, stmt in enumerate(statements):
        if not isinstance(stmt, dict):
            continue
        _check_freshness(stmt, idx, doc_ts, now, errors)
        _check_impact_statement(stmt, idx, errors)

    if errors:
        sys.stderr.write(f"{VEX_FILE} local-policy violations:\n")
        for err in errors:
            sys.stderr.write(f"  {err}\n")
        sys.stderr.write(
            f"\nLocal policy: every statement's `last_updated` must be "
            f"within the last {MAX_AGE_DAYS} days, and `not_affected` "
            f"statements must carry a free-text `impact_statement`. "
            f"Structural validation (required fields, enums, conditional "
            f"constraints) is performed separately by the `vex-schema` "
            f"pre-commit hook against the upstream OpenVEX "
            f"schema."
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
