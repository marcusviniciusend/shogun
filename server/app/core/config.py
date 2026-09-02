"""Configuração do servidor, lida a partir de variáveis de ambiente / .env."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    # Integração com a API da Anthropic
    anthropic_api_key: str = ""
    shogun_model: str = "claude-opus-5"
    # Teto de tokens da resposta do modelo por comando.
    shogun_max_tokens: int = 2048

    # Autenticação: token fixo (Bearer) compartilhado com os clientes.
    # Vazio = autenticação desligada (apenas para desenvolvimento local).
    shogun_auth_token: str = ""

    # Host/porta do servidor
    shogun_host: str = "0.0.0.0"
    shogun_port: int = 8000


settings = Settings()
