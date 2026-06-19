"""Entry point of the project."""

from __future__ import annotations

import sys

import structlog

from .config import get_config
from .utils import configure_logging

logger = structlog.get_logger(__name__)


def main() -> int:
    """Bootstrap logging, load configuration, and hand off to application code."""
    cfg = get_config()
    configure_logging(level=cfg.logging.level, fmt=cfg.logging.format)

    logger.info(
        "configuration_loaded",
        my_config_field=cfg.my_config_field,
        my_secret=cfg.my_secret,
    )

    # Replace this with your application's entry point.
    return 0


if __name__ == "__main__":
    sys.exit(main())
