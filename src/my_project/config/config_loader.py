"""Load YAML configuration via OmegaConf and validate with Pydantic."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from omegaconf import OmegaConf

from .config import Config

_DEFAULT_CONFIG_PATH = Path.cwd() / "config" / "config.yaml"
_DEFAULT_ENV_FILE_PATH = Path.cwd() / "config" / ".env"
# => code must run from repo root

# Sentinel env var (set in the shipped Dockerfile) that disables the implicit
# `config/.env` fallback. Containers receive env vars from the runtime
# (`docker run --env-file`, Compose `env_file:`, k8s Secrets, …), so a baked-in
# dotenv file is the wrong source of truth. The dunder-style name is unlikely
# to collide with any real-world env var.
_DOTENV_DISABLED_ENV_VAR = "__DISABLE_LOAD_DOTENV__"
_TRUTHY_VALUES = frozenset({"1", "true", "yes"})


def _dotenv_disabled() -> bool:
    """True when the default `config/.env` fallback should be skipped.

    Driven by the ``__DISABLE_LOAD_DOTENV__`` env var (truthy: ``1``, ``true``,
    ``yes``, case-insensitive). The shipped Dockerfile sets this so production
    containers don't silently mask runtime-supplied env vars with whatever
    happens to (or fails to) live on disk inside the image.

    Explicit ``env_file=`` arguments to :func:`load_config` always take
    precedence and ignore this flag.
    """
    return os.environ.get(_DOTENV_DISABLED_ENV_VAR, "").strip().lower() in _TRUTHY_VALUES


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
            ignored when missing). Defaults to None. The default fallback is
            also skipped when ``__DISABLE_LOAD_DOTENV__`` is truthy in the
            environment — the shipped Dockerfile sets this so containerized
            runs don't load a stale baked-in dotenv on top of runtime-supplied
            env vars.

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
    elif not _dotenv_disabled():
        load_dotenv(_DEFAULT_ENV_FILE_PATH, override=True)

    cfg = OmegaConf.load(config_path)
    raw: dict[str, Any] = OmegaConf.to_container(cfg, resolve=True)  # ty: ignore[invalid-assignment]
    return Config.model_validate(raw)


@lru_cache(maxsize=1)
def get_config() -> Config:
    """Return basic configuration."""
    return load_config()
