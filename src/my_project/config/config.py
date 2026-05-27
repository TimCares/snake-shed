"""Pydantic configuration schemas for the application.

Each nested model maps to a section in `config/config.yaml`.  Values are
resolved from environment variables via OmegaConf's `${oc.env:...}`
interpolation before Pydantic validates them.
"""

from typing import Literal

from pydantic import BaseModel, Field, SecretStr

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
LogFormat = Literal["console", "json"]


class LoggingConfig(BaseModel):
    """Logging level and output format (see `config/config.yaml`)."""

    level: LogLevel = Field(default="INFO", description="Minimum log level")
    format: LogFormat = Field(
        default="console",
        description="Encouraged: `console` for dev, `json` for production log collectors",
    )


class Config(BaseModel):
    """Root configuration validated by Pydantic."""

    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    my_config_field: str = Field(..., description="My config field")
    my_env: str = Field(..., description="My env")
    my_secret: SecretStr = Field(..., description="My secret")
