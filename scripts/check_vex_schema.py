"""Validate openvex.json against upstream OpenVEX schema with local allowance.

The OpenVEX upstream schema currently requires `statements` to be non-empty.
This project allows `statements: []` to represent "no known vulnerabilities".
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from jsonschema import FormatChecker, ValidationError, validators

VEX_FILE = Path("openvex.json")
SCHEMA_URL = "https://raw.githubusercontent.com/openvex/spec/main/openvex_json_schema.json"


def _json_path(parts: list[Any]) -> str:
    """Convert an error path list to a compact JSONPath-like string."""
    path = "$"
    for part in parts:
        if isinstance(part, int):
            path += f"[{part}]"
        elif isinstance(part, str) and part.isidentifier():
            path += f".{part}"
        else:
            path += f"[{part!r}]"
    return path


def _load_schema() -> dict[str, Any]:
    """Fetch and parse the upstream OpenVEX schema."""
    with urlopen(SCHEMA_URL, timeout=20) as response:  # noqa: S310
        data = response.read()
    schema = json.loads(data)
    if not isinstance(schema, dict):
        msg = f"{SCHEMA_URL}: schema root is not a JSON object"
        raise TypeError(msg)
    return schema


def _allow_empty_statements(schema: dict[str, Any]) -> None:
    """Patch schema in-memory to allow statements: [] for this project."""
    props = schema.get("properties")
    if not isinstance(props, dict):
        return
    statements = props.get("statements")
    if not isinstance(statements, dict):
        return
    statements["minItems"] = 0


def _validate(doc: Any, schema: dict[str, Any]) -> list[ValidationError]:
    """Return sorted validation errors for deterministic output."""
    validator_cls = validators.validator_for(schema)
    validator_cls.check_schema(schema)
    validator = validator_cls(schema, format_checker=FormatChecker())
    return sorted(validator.iter_errors(doc), key=lambda err: list(err.path))


def main() -> int:
    """Validate `openvex.json` and print diagnostics to stderr."""
    if not VEX_FILE.exists():
        return 0

    try:
        doc = json.loads(VEX_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"{VEX_FILE}: cannot read VEX document ({exc})\n")
        return 1

    try:
        schema = _load_schema()
    except (URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"{VEX_FILE}: cannot load OpenVEX schema ({exc})\n")
        return 1

    _allow_empty_statements(schema)

    try:
        errors = _validate(doc, schema)
    except Exception as exc:  # pragma: no cover
        sys.stderr.write(f"{VEX_FILE}: schema validation runtime error ({exc})\n")
        return 1

    if not errors:
        return 0

    sys.stderr.write("Schema validation errors were encountered.\n")
    for err in errors:
        pointer = _json_path(list(err.path))
        sys.stderr.write(f"  {VEX_FILE}::{pointer}: {err.message}\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
