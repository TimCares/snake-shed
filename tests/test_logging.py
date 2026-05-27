"""Tests for structlog / stdlib logging setup."""

from __future__ import annotations

import json
import logging

import structlog

from my_project.utils.logging import configure_logging


def test_configure_logging_json_emits_parseable_records(capsys) -> None:
    configure_logging(level="INFO", fmt="json")
    log = structlog.get_logger("test_logging")
    log.info("hello", answer=42)

    out = capsys.readouterr().out.strip()
    record = json.loads(out)

    assert record["event"] == "hello"
    assert record["answer"] == 42
    assert record["level"] == "info"
    assert record["logger"] == "test_logging"


def test_configure_logging_routes_foreign_stdlib_loggers(capsys) -> None:
    configure_logging(level="INFO", fmt="json")
    logging.getLogger("urllib3").warning("foreign", extra={"detail": "x"})

    out = capsys.readouterr().out.strip()
    record = json.loads(out)

    assert record["event"] == "foreign"
    assert record["level"] == "warning"
    assert record["logger"] == "urllib3"
