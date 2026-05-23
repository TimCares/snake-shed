"""Entry point so the package can be run as ``python -m my_project``."""

from __future__ import annotations

import logging
import sys

from .config import get_config

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s - %(message)s"


def main() -> int:
    """Bootstrap logging, load configuration, and hand off to application code."""
    logging.basicConfig(level=logging.INFO, format=_LOG_FORMAT)
    log = logging.getLogger(__name__)

    cfg = get_config()
    log.info(
        "configuration loaded (my_config_field=%s, my_env=%s)",
        cfg.my_config_field,
        cfg.my_env,
    )

    # Replace this with your application's entry point.
    return 0


if __name__ == "__main__":
    sys.exit(main())
