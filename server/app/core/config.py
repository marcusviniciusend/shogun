"""Configuração do servidor, lida a partir de variáveis de ambiente / .env."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    # --- Provedor de LLM ---------------------------------------------------
    # Nome registrado em app.core.llm.PROVIDERS.
    shogun_llm_provider: str = "claude"
    # Provedor acionado quando o principal falha. Vazio = sem fallback.
    shogun_llm_fallback_provider: str = ""
    # Teto de tokens da resposta do modelo por comando.
    shogun_max_tokens: int = 2048
    # Timeout (segundos) das chamadas ao LLM — curto o bastante para o fallback
    # entrar em ação antes de o cliente desistir.
    shogun_llm_timeout: float = 30.0

    # --- Credenciais e modelos por provedor --------------------------------
    anthropic_api_key: str = ""
    shogun_model: str = "claude-opus-5"

    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"

    openai_api_key: str = ""
    openai_mini_model: str = "gpt-4o-mini"

    # --- Autenticação dos clientes -----------------------------------------
    # Token fixo (Bearer) compartilhado com os clientes.
    # Vazio = autenticação desligada (apenas para desenvolvimento local).
    shogun_auth_token: str = ""

    # --- Servidor ----------------------------------------------------------
    shogun_host: str = "0.0.0.0"
    shogun_port: int = 8000


settings = Settings()
