from functools import lru_cache

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    api_key: SecretStr
    legacy_api_key_enabled: bool = False

    model_config = SettingsConfigDict(env_prefix="OIP_", extra="ignore")

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        if len(raw) < 32 or raw.startswith("replace_with_"):
            raise ValueError("OIP_API_KEY doit être un secret aléatoire d'au moins 32 caractères")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
