"""Enforce repo-level policy on ``.trivyignore`` entries.

Policy
------
1. Every suppression line must match ``<CVE-or-GHSA-ID> exp:YYYY-MM-DD``.
2. The previous non-empty line must be a ``#`` comment — the justification.

Exit code 0 means policy is satisfied (or no ``.trivyignore`` exists).
Exit code 1 means at least one entry violates the policy; diagnostics are
written to stderr with ``path:line`` prefixes so editors / CI can navigate
to the offending line.

Invoked by the ``trivyignore-check`` pre-commit hook and by
``make trivyignore-check``. Pure stdlib — no project deps required.
"""

from __future__ import annotations

import datetime as dt
import re
import sys
from pathlib import Path

IGNORE_FILE = Path(".trivyignore")
DEFAULT_EXPIRY_DAYS = 180

_BARE_ID_PATTERN = re.compile(r"^(CVE-\d{4}-\d{4,}|GHSA-[\w-]+)$")
_ENTRY_PATTERN = re.compile(
    r"^(?P<id>CVE-\d{4}-\d{4,}|GHSA-[\w-]+)\s+exp:(?P<date>\d{4}-\d{2}-\d{2})\s*$"
)


def _validate(lines: list[str]) -> list[str]:
    """Walk the file and return one human-readable diagnostic per violation.

    Args:
        lines: Raw lines from ``.trivyignore`` (newlines already stripped).

    Returns:
        Empty list when the policy is satisfied; otherwise one diagnostic
        per violation, in the order encountered.
    """
    errors: list[str] = []
    suggested_exp = dt.date.today() + dt.timedelta(days=DEFAULT_EXPIRY_DAYS)  # noqa: DTZ011

    for i, raw in enumerate(lines):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue

        entry_match = _ENTRY_PATTERN.match(stripped)
        if not entry_match:
            if _BARE_ID_PATTERN.match(stripped):
                errors.append(
                    f"{IGNORE_FILE}:{i + 1}: missing expiry — "
                    f"add `exp:YYYY-MM-DD` (suggest {suggested_exp})"
                )
            else:
                errors.append(
                    f"{IGNORE_FILE}:{i + 1}: unrecognised line "
                    f"`{stripped}` — expected "
                    f"`<CVE-... or GHSA-...> exp:YYYY-MM-DD`"
                )
            continue

        try:
            dt.date.fromisoformat(entry_match.group("date"))
        except ValueError:
            errors.append(
                f"{IGNORE_FILE}:{i + 1}: invalid date "
                f"`{entry_match.group('date')}` — use ISO 8601 (YYYY-MM-DD)"
            )

        prev_idx = i - 1
        while prev_idx >= 0 and not lines[prev_idx].strip():
            prev_idx -= 1
        if prev_idx < 0 or not lines[prev_idx].strip().startswith("#"):
            errors.append(
                f"{IGNORE_FILE}:{i + 1}: missing justification — "
                f"add a `# ...` comment ABOVE this line explaining "
                f"why the CVE is non-applicable here"
            )

    return errors


def main() -> int:
    """Validate ``.trivyignore`` against the policy.

    Returns:
        0 on success (policy satisfied or file missing), 1 on violations.
    """
    if not IGNORE_FILE.exists():
        return 0

    lines = IGNORE_FILE.read_text(encoding="utf-8").splitlines()
    errors = _validate(lines)

    if errors:
        sys.stderr.write(f"{IGNORE_FILE} policy violations:\n")
        for err in errors:
            sys.stderr.write(f"  {err}\n")
        sys.stderr.write(
            "\nPolicy: every entry needs a justification comment above it "
            "AND an `exp:YYYY-MM-DD` suffix. See the file's header for full "
            "rationale.\n"
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
