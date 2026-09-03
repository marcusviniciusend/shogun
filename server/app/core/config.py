"""Configuração do servidor, lida a partir de variáveis de ambiente / .env."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    anthropic_api_key: str = ""
    shogun_model: str = "claude-sonnet-5"
    shogun_host: str = "0.0.0.0"
    shogun_port: int = 8000


settings = Settings()
