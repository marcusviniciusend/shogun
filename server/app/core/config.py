"""Configuração do servidor, lida a partir de variáveis de ambiente / .env."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    # --- Provedor de LLM ---------------------------------------------------
    # Nome registrado em app.core.llm.PROVIDERS:
    # claude | deepseek | openai_mini | ollama
    shogun_llm_provider: str = "claude"
    # Provedor acionado quando o principal falha. Vazio = sem fallback.
    shogun_llm_fallback_provider: str = ""
    # Teto de tokens da resposta do modelo por comando. Nos modelos com thinking
    # adaptativo (Opus 5) os tokens de raciocinio saem deste mesmo teto, entao a
    # folga aqui evita truncar uma resposta que, em si, e curta.
    shogun_max_tokens: int = 4096
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

    # Ollama roda local e nao usa credencial — so endereco e nome do modelo.
    # `ollama_model` nao tem default de proposito: qual modelo local usar e uma
    # escolha com consequencia (VRAM, qualidade do JSON), e um default silencioso
    # esconderia essa escolha. Sem valor, o servidor sobe normalmente — quem
    # reclama e o OllamaProvider, e so quando o ollama e o provedor em uso.
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = ""

    # --- Autenticação dos clientes -----------------------------------------
    # Token fixo (Bearer) compartilhado com os clientes.
    # Vazio = autenticação desligada (apenas para desenvolvimento local).
    shogun_auth_token: str = ""

    # --- Servidor ----------------------------------------------------------
    shogun_host: str = "0.0.0.0"
    shogun_port: int = 8000


settings = Settings()
