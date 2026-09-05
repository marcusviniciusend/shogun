"""Configuração do servidor, lida a partir de variáveis de ambiente / .env."""

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.rede import BindEfetivo

# Enderecos que so o proprio computador alcanca. Escutar em qualquer coisa fora
# desta lista significa aceitar conexao de outra maquina.
HOSTS_LOCAIS = frozenset({"127.0.0.1", "localhost", "::1"})


def host_exposto(host: str) -> bool:
    """True quando `host` aceita conexao vinda de outra maquina."""
    return host.strip().lower() not in HOSTS_LOCAIS


class ConfiguracaoInseguraError(RuntimeError):
    """Configuracao que exporia o servidor sem autenticacao.

    Levantada antes de o servidor comecar a escutar — e melhor nao subir do que
    subir aberto.
    """


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
    # `0.0.0.0` escuta em todas as interfaces — necessario para os clientes
    # remotos (mobile via Tailscale) alcancarem o servidor. Para restringir a
    # maquina local, use SHOGUN_HOST=127.0.0.1.
    shogun_host: str = "0.0.0.0"
    shogun_port: int = 8000

    # --- Banco de dados ----------------------------------------------------
    # Arquivo relativo ao diretorio de onde o servidor e iniciado (server/).
    # O schema e criado pelo Alembic: `alembic upgrade head`.
    shogun_database_url: str = "sqlite:///./shogun.db"
    # Quantas mensagens do historico entram no prompt. Janela por contagem, nao
    # por orcamento de tokens: o limite precisa caber no menor contexto entre os
    # provedores (o modelo local), e contar mensagem e previsivel sem tokenizer.
    shogun_historico_max_mensagens: int = 20

    # --- CORS --------------------------------------------------------------
    # Origens permitidas, separadas por virgula. Vazio = CORS desligado, que e
    # o correto para os clientes atuais: desktop (Tauri) e mobile (React
    # Native) falam HTTP direto, sem origem de navegador, e nao disparam
    # preflight. Preencha so quando houver um cliente rodando em navegador
    # — ex.: http://100.101.102.103:8000 (IP Tailscale desta maquina).
    shogun_allowed_origins: str = ""

    @property
    def allowed_origins(self) -> list[str]:
        """`shogun_allowed_origins` como lista, sem entradas vazias."""
        return [o.strip() for o in self.shogun_allowed_origins.split(",") if o.strip()]

    @property
    def exposto_na_rede(self) -> bool:
        """True quando `SHOGUN_HOST` aceita conexao de outra maquina.

        Atalho para o caso comum. Quem valida o startup usa `validar_exposicao`
        com o bind real, que pode divergir desta variavel.
        """
        return host_exposto(self.shogun_host)

    def validar_exposicao(self, bind: "BindEfetivo | None" = None) -> None:
        """Recusa a combinacao "aberto para a rede" + "sem autenticacao".

        `bind` e o host que o servidor realmente vai escutar, com a origem da
        informacao (ver `app.core.rede.descobrir_bind`). Sem ele, cai para
        `SHOGUN_HOST` — util em checagem estatica de configuracao, fora de um
        servidor rodando.

        Em bind local o token continua opcional: so o proprio computador
        alcanca o servidor, e exigir token ali atrapalharia o desenvolvimento
        sem proteger nada.
        """
        if bind is None:
            bind = BindEfetivo(self.shogun_host, "SHOGUN_HOST")

        if host_exposto(bind.host) and not self.shogun_auth_token:
            raise ConfiguracaoInseguraError(
                f"o servidor vai escutar em {bind.host}, vindo de "
                f"{bind.origem}, o que aceita conexoes de outras maquinas - "
                "mas SHOGUN_AUTH_TOKEN esta vazio, entao ele ficaria aberto a "
                "quem alcancasse a porta. Defina SHOGUN_AUTH_TOKEN, ou escute "
                "em 127.0.0.1 para desenvolvimento local sem token."
            )


settings = Settings()
