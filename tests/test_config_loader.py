"""Tests for configuration loading and version metadata."""

from __future__ import annotations

from pathlib import Path

import pytest

from my_project.config import config_loader
from my_project.config import get_config, load_config


def _write_config(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "my_config_field: configured-value",
                "my_env: ${oc.env:MY_ENV}",
                "my_secret: ${oc.env:MY_SECRET}",
            ]
        ),
        encoding="utf-8",
    )


def test_load_config_with_explicit_env_file(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    env_file = tmp_path / ".env"

    _write_config(config_path)
    env_file.write_text("MY_ENV=from-dotenv\nMY_SECRET=super-secret\n", encoding="utf-8")

    loaded = load_config(str(config_path), str(env_file))

    assert loaded.my_config_field == "configured-value"
    assert loaded.my_env == "from-dotenv"
    assert loaded.my_secret.get_secret_value() == "super-secret"


def test_load_config_raises_for_missing_explicit_env_file(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"

    _write_config(config_path)

    with pytest.raises(FileNotFoundError, match="Env file not found"):
        load_config(str(config_path), str(tmp_path / "missing.env"))


def test_get_config_uses_defaults_and_optional_missing_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"

    _write_config(config_path)

    monkeypatch.setattr(config_loader, "_DEFAULT_CONFIG_PATH", config_path)
    monkeypatch.setattr(config_loader, "_DEFAULT_ENV_FILE_PATH", tmp_path / ".env")
    monkeypatch.setenv("MY_ENV", "from-environment")
    monkeypatch.setenv("MY_SECRET", "another-secret")
    get_config.cache_clear()

    loaded = get_config()
    loaded_again = get_config()

    assert loaded is loaded_again
    assert loaded.my_env == "from-environment"
    assert loaded.my_secret.get_secret_value() == "another-secret"

    get_config.cache_clear()
