"""Strategies for providing secrets to the application via the config.

External secrets managers can be integrated with e.g.::

class ManagedSecretRef(SecretRefBase):
    '''Secret managed by an external secrets manager.

    Example are: Hashicorp Vault, AWS Secrets Manager, Azure Key Vault.
    '''
    provider: Literal["secret_manager"] = "secret_manager"
    name: str

    def _load(self) -> str:
        '''Load the secret from the secret manager.'''
        # your code here
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pathlib import Path  # noqa: TC003 -> pydantic needs it
from threading import RLock
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, SecretStr


class SecretRefBase(BaseModel, ABC):
    """Abstract Pydantic model for cached secrets from different providers."""

    model_config = ConfigDict(extra="forbid")

    provider: str

    _value: SecretStr | None = PrivateAttr(default=None)
    _lock: RLock = PrivateAttr(default_factory=RLock)

    @abstractmethod
    def _load(self) -> str:
        """Load the secret from the concrete provider."""
        raise NotImplementedError

    def get(self) -> str:
        """Return the cached secret value.

        The secret is loaded lazily. Call reload() to refresh it.
        """
        with self._lock:
            if self._value is None:
                self._value = SecretStr(self._load())

            return self._value.get_secret_value()

    def reload(self) -> None:
        """Reload the secret using the provider strategy."""
        new_value = self._load()

        if new_value == "":
            raise ValueError("Secret value must not be empty")

        with self._lock:
            self._value = SecretStr(new_value)

    def clear_cache(self) -> None:
        """Drop the cached secret reference."""
        with self._lock:
            self._value = None


class EnvSecretRef(SecretRefBase):
    """Secret loaded from an environment variable."""

    provider: Literal["env"] = "env"
    name: str

    def _load(self) -> str:
        """Load the secret from an environment variable."""
        try:
            return os.environ[self.name]
        except KeyError as e:
            raise RuntimeError(
                f"Required secret environment variable '{self.name}' is not set"
            ) from e


class FileSecretRef(SecretRefBase):
    """Secret loaded from file contents."""

    provider: Literal["file"] = "file"
    path: Path

    def _load(self) -> str:
        """Load the secret from a file."""
        try:
            return self.path.read_text(encoding="utf-8").rstrip("\r\n")
        except FileNotFoundError as e:
            raise RuntimeError(f"Required secret file '{self.path}' does not exist") from e
        except PermissionError as e:
            raise RuntimeError(f"Permission denied reading secret file '{self.path}'") from e


SecretRef = Annotated[
    EnvSecretRef | FileSecretRef,
    Field(discriminator="provider"),
]
