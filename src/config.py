"""Pydantic configuration schemas for the application.

Each nested model maps to a section in `config/config.yaml`.  Values are
resolved from environment variables via OmegaConf's `${oc.env:...}`
interpolation before Pydantic validates them.
"""

from pydantic import BaseModel, Field, SecretStr


class Config(BaseModel):
    """Root configuration validated by Pydantic."""

    my_config_field: str = Field(..., description="My config field")
    my_env: str = Field(..., description="My env")
    my_secret: SecretStr = Field(..., description="My secret")
