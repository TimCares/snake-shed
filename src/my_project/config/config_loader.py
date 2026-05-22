"""Load YAML configuration via OmegaConf and validate with Pydantic."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from omegaconf import OmegaConf

from .config import Config

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_CONFIG_PATH = _PROJECT_ROOT / "config" / "config.yaml"
_DEFAULT_ENV_FILE_PATH = _PROJECT_ROOT / "config" / ".env"


def load_config(
    config_path: str | None = None,
    env_file: str | None = None,
) -> Config:
    """Load YAML config, resolve env-var interpolation, and validate.

    Args:
        config_path (str | None, optional): Path to the OmegaConf YAML file.
            If None, will be `config/config.yaml` from the project root.
            Defaults to None.
        env_file (str | None, optional): Optional `.env` file to load before resolving.
            If None, falls back to `config/.env` from the project root (silently
            ignored when missing). Defaults to None.

    Raises:
        FileNotFoundError: If `env_file` is explicitly provided but the file does not exist.

    Returns:
        Config: Fully validated configuration.
    """
    if config_path is None:
        config_path = str(_DEFAULT_CONFIG_PATH)

    if env_file is not None:
        env_path = Path(env_file)
        if not env_path.is_file():
            msg = f"Env file not found: {env_path}"
            raise FileNotFoundError(msg)
        load_dotenv(env_path, override=True)
    else:
        load_dotenv(_DEFAULT_ENV_FILE_PATH, override=True)

    cfg = OmegaConf.load(config_path)
    raw: dict[str, Any] = OmegaConf.to_container(cfg, resolve=True)  # ty: ignore[invalid-assignment]
    return Config.model_validate(raw)


@lru_cache(maxsize=1)
def get_config() -> Config:
    """Return basic configuration."""
    return load_config()
