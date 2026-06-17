"""Load YAML configuration and validate with Pydantic."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from .config import Config

_DEFAULT_CONFIG_PATH = Path.cwd() / "config" / "config.yaml"


def load_config(
    config_path: str | None = None,
) -> Config:
    """Load YAML config, resolve env-var interpolation, and validate.

    Args:
        config_path (str | None, optional): Path to the YAML file.
            If None, will be `config/config.yaml` from the project root.
            Defaults to None.

    Returns:
        Config: Fully validated configuration.
    """
    if config_path is None:
        config_path = str(_DEFAULT_CONFIG_PATH)

    with open(config_path, mode="rb") as file:
        raw = yaml.safe_load(file)
    return Config.model_validate(raw)


@lru_cache(maxsize=1)
def get_config() -> Config:
    """Return basic configuration."""
    return load_config()
