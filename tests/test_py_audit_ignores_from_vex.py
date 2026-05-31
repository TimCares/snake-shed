"""Tests for the OpenVEX-to-uv-audit shim."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest


def _load_script_module() -> ModuleType:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "py_audit_ignores_from_vex.py"
    spec = importlib.util.spec_from_file_location("py_audit_ignores_from_vex", script_path)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_main_prints_ignore_flags_for_filterable_pypi_statements(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    vex_file = tmp_path / "openvex.json"
    vex_file.write_text(
        json.dumps(
            {
                "statements": [
                    {
                        "vulnerability": {
                            "name": "CVE-2024-0001",
                            "aliases": ["GHSA-aaaa-bbbb-cccc", "PYSEC-2024-0001"],
                        },
                        "products": [{"@id": "pkg:pypi/demo"}],
                        "status": "not_affected",
                    },
                    {
                        "vulnerability": {"name": "PYSEC-2024-0002"},
                        "products": [{"@id": "pkg:pypi/demo"}],
                        "status": "fixed",
                    },
                    {
                        "vulnerability": {"name": "CVE-2024-9999"},
                        "products": [{"@id": "pkg:deb/debian/openssl@1.0"}],
                        "status": "not_affected",
                    },
                    {
                        "vulnerability": {"name": "CVE-2024-1111"},
                        "products": [{"@id": "pkg:pypi/demo"}],
                        "status": "affected",
                    },
                    {
                        "vulnerability": {
                            "name": "GHSA-aaaa-bbbb-cccc",
                            "aliases": ["PYSEC-2024-0001", "CVE-2024-0001"],
                        },
                        "products": [{"@id": "pkg:pypi/demo"}],
                        "status": "fixed",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    module = _load_script_module()
    monkeypatch.setattr(module, "VEX_FILE", vex_file)

    assert module.main() == 0
    assert capsys.readouterr().out == "--ignore PYSEC-2024-0001 --ignore PYSEC-2024-0002"