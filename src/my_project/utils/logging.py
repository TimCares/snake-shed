"""Configure structlog and stdlib logging for consistent, structured output."""

from __future__ import annotations

import importlib.metadata
import logging
import sys
import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Literal

import structlog

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
LogFormat = Literal["console", "json"]

_ROOT_PACKAGE = __name__.rsplit(".", 2)[0]


@lru_cache(maxsize=1)
def _project_identity() -> tuple[str, str]:
    """Return `(service, version)` from `pyproject.toml` or installed metadata."""
    pyproject = _find_pyproject_toml()
    if pyproject is not None:
        data = tomllib.load(pyproject.open("rb"))
        project = data["project"]
        return project["name"], project["version"]

    dist_name = _distribution_name()
    meta = importlib.metadata.metadata(dist_name)
    return meta["Name"], importlib.metadata.version(dist_name)


def _find_pyproject_toml() -> Path | None:
    """Locate `pyproject.toml` by walking up from this file (dev / repo root)."""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "pyproject.toml"
        if candidate.is_file():
            return candidate
    return None


def _distribution_name() -> str:
    """Resolve the installed distribution name for the root package."""
    mapping = importlib.metadata.packages_distributions()
    names = mapping.get(_ROOT_PACKAGE)
    if not names:
        msg = f"No distribution found for package {_ROOT_PACKAGE!r}"
        raise RuntimeError(msg)
    return names[0]


def configure_logging(*, level: LogLevel, fmt: LogFormat) -> None:
    """Wire structlog and the stdlib root logger through one formatter pipeline.

    Args:
        level: Minimum log level for the root logger (e.g. `INFO`).
        fmt: `console` for human-readable dev output; `json` for log collectors.
    """
    log_level = getattr(logging, level)

    timestamper = structlog.processors.TimeStamper(fmt="iso")
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        timestamper,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer() if fmt == "json" else structlog.dev.ConsoleRenderer()
    )

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(log_level)

    service, version = _project_identity()
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(service=service, version=version)
