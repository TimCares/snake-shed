"""Load YAML configuration via OmegaConf and validate with Pydantic."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from omegaconf import OmegaConf

from src.config import Config

_DEFAULT_CONFIG_PATH = Path("config/config.yaml")
_DEFAULT_ENV_FILE_PATH = Path(__file__).parent.parent.resolve() / "config" / ".env"


def load_config(
    config_path: Path = _DEFAULT_CONFIG_PATH,
    env_file: Path | None = _DEFAULT_ENV_FILE_PATH,
) -> Config:
    """Load YAML config, resolve env-var interpolation, and validate.

    Args:
        config_path (Path, optional): Path to the OmegaConf YAML file. Defaults to `config/config.yaml`.
        env_file (Path, optional): Optional `.env` file to load before resolving.
            Defaults to, relative to the project root, `config/.env`.

    Returns:
        Fully validated configuration.
    """
    if env_file is not None:
        load_dotenv(env_file, override=True)

    cfg = OmegaConf.load(config_path)
    raw: dict[str, Any] = OmegaConf.to_container(cfg, resolve=True)  # type: ignore[assignment]
    return Config.model_validate(raw)


@lru_cache(maxsize=1)
def get_config() -> Config:
    """Return cached configuration."""
    return load_config()
