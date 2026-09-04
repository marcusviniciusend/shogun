"""Testes dos provedores de LLM, do registro e do fallback — tudo com mocks."""

import json
from types import SimpleNamespace

import anthropic
import httpx

import pytest
from openai import APITimeoutError, RateLimitError

from app.core.config import Settings
from app.core.llm import (
    ESQUEMA_COMANDO,
    PROVIDERS,
    SYSTEM_PROMPT,
    ClaudeProvider,
    ComandoInterpretado,
    DeepSeekProvider,
    FallbackLLMProvider,
    LLMIndisponivelError,
    LLMProvider,
    OllamaProvider,
    OpenAIMiniProvider,
    ProviderDesconhecidoError,
    criar_provider,
    montar_provider,
)

RESPOSTA_JSON = json.dumps(
    {
        "acao": "abrir_app",
        "parametros": {"app": "Spotify", "limite": None},
        "resposta_falada": "Abrindo o Spotify, Marcus.",
    }
)


def _resposta_openai(conteudo, finish_reason="stop", refusal=None):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=conteudo, refusal=refusal),
                finish_reason=finish_reason,
            )
        ]
    )


class ChatFake:
    """Substitui client.chat.completions e guarda os kwargs recebidos."""

    def __init__(self, resposta=None, erro: Exception | None = None):
        self.resposta = resposta
        self.erro = erro
        self.kwargs: dict = {}

    async def create(self, **kwargs):
        self.kwargs = kwargs
        if self.erro is not None:
            raise self.erro
        return self.resposta


def _mockar(provider, resposta=None, erro=None) -> ChatFake:
    chat = ChatFake(resposta, erro)
    provider._client = SimpleNamespace(chat=SimpleNamespace(completions=chat))
    return chat


@pytest.fixture
def config() -> Settings:
    # _env_file=None isola os testes de um .env real na maquina do desenvolvedor.
    return Settings(
        _env_file=None,
        anthropic_api_key="ant-x",
        deepseek_api_key="ds-x",
        openai_api_key="oa-x",
        # OLLAMA_MODEL nao tem default: sem isso o OllamaProvider nem constroi.
        ollama_model="hermes3:8b",
    )


# --- schema compartilhado ------------------------------------------------


def test_schema_e_fechado_em_todos_os_objetos():
    """Anthropic e o strict mode da OpenAI rejeitam objetos abertos."""

    def visitar(no):
        if isinstance(no, dict):
            if no.get("type") == "object":
                assert no.get("additionalProperties") is False
                assert set(no["required"]) == set(no["properties"])
            for valor in no.values():
                visitar(valor)
        elif isinstance(no, list):
            for item in no:
                visitar(item)

    visitar(ESQUEMA_COMANDO)


# --- DeepSeek ------------------------------------------------------------


def test_deepseek_usa_endpoint_e_modelo_proprios(config):
    provider = DeepSeekProvider(config)
    assert provider.nome == "deepseek"
    assert provider.base_url == "https://api.deepseek.com"
    assert provider._modelo == "deepseek-chat"
    assert provider.configurado


async def test_deepseek_pede_json_mode_e_descreve_o_schema_no_prompt(config):
    provider = DeepSeekProvider(config)
    chat = _mockar(provider, _resposta_openai(RESPOSTA_JSON))

    comando = await provider.interpretar_comando("abre o spotify")

    assert chat.kwargs["response_format"] == {"type": "json_object"}
    assert chat.kwargs["model"] == "deepseek-chat"
    sistema = chat.kwargs["messages"][0]["content"]
    # A personalidade e identica; o schema entra como acrescimo, nao como troca.
    assert sistema.startswith(SYSTEM_PROMPT)
    assert "resposta_falada" in sistema
    assert chat.kwargs["messages"][1] == {"role": "user", "content": "abre o spotify"}
    assert comando.acao == "abrir_app"
    # Campos nulos do schema fechado somem do dict publico.
    assert comando.parametros == {"app": "Spotify"}


async def test_deepseek_sem_chave_falha_sem_chamar_api():
    provider = DeepSeekProvider(Settings(_env_file=None, deepseek_api_key=""))
    assert not provider.configurado
    with pytest.raises(LLMIndisponivelError, match="deepseek"):
        await provider.interpretar_comando("oi")


async def test_deepseek_converte_rate_limit_em_erro_do_dominio(config):
    provider = DeepSeekProvider(config)
    _mockar(
        provider,
        erro=RateLimitError(
            "limite",
            response=SimpleNamespace(status_code=429, headers={}, request=None),
            body=None,
        ),
    )
    with pytest.raises(LLMIndisponivelError, match="deepseek"):
        await provider.interpretar_comando("oi")


async def test_json_invalido_vira_erro_do_dominio(config):
    provider = DeepSeekProvider(config)
    _mockar(provider, _resposta_openai("isso nao e json"))
    with pytest.raises(LLMIndisponivelError, match="JSON"):
        await provider.interpretar_comando("oi")


async def test_json_valido_fora_do_schema_vira_erro_do_dominio(config):
    provider = DeepSeekProvider(config)
    _mockar(provider, _resposta_openai(json.dumps({"acao": "dancar"})))
    with pytest.raises(LLMIndisponivelError, match="formato"):
        await provider.interpretar_comando("oi")


# --- OpenAI mini ---------------------------------------------------------


async def test_openai_mini_usa_structured_output_nativo(config):
    provider = OpenAIMiniProvider(config)
    chat = _mockar(provider, _resposta_openai(RESPOSTA_JSON))

    comando = await provider.interpretar_comando("abre o spotify")

    formato = chat.kwargs["response_format"]
    assert formato["type"] == "json_schema"
    assert formato["json_schema"]["strict"] is True
    assert formato["json_schema"]["schema"] == ESQUEMA_COMANDO
    assert chat.kwargs["model"] == "gpt-4o-mini"
    # Com o schema imposto pela API, o prompt e a personalidade pura.
    assert chat.kwargs["messages"][0]["content"] == SYSTEM_PROMPT
    assert comando.resposta_falada == "Abrindo o Spotify, Marcus."


def test_openai_mini_usa_endpoint_padrao(config):
    assert OpenAIMiniProvider(config).base_url is None


async def test_recusa_do_modelo_vira_erro_do_dominio(config):
    provider = OpenAIMiniProvider(config)
    _mockar(provider, _resposta_openai(None, refusal="nao posso ajudar"))
    with pytest.raises(LLMIndisponivelError, match="nao posso ajudar"):
        await provider.interpretar_comando("oi")


async def test_resposta_truncada_vira_erro_do_dominio(config):
    provider = OpenAIMiniProvider(config)
    _mockar(provider, _resposta_openai(RESPOSTA_JSON, finish_reason="length"))
    with pytest.raises(LLMIndisponivelError, match="SHOGUN_MAX_TOKENS"):
        await provider.interpretar_comando("oi")


# --- Claude ---------------------------------------------------------------


def _resposta_claude(texto, stop_reason="end_turn", stop_details=None):
    conteudo = [SimpleNamespace(type="text", text=texto)] if texto is not None else []
    return SimpleNamespace(
        content=conteudo, stop_reason=stop_reason, stop_details=stop_details
    )


class MessagesFake:
    """Substitui client.messages e guarda os kwargs recebidos."""

    def __init__(self, resposta=None, erro: Exception | None = None):
        self.resposta = resposta
        self.erro = erro
        self.kwargs: dict = {}

    async def create(self, **kwargs):
        self.kwargs = kwargs
        if self.erro is not None:
            raise self.erro
        return self.resposta


def _mockar_claude(provider, resposta=None, erro=None) -> MessagesFake:
    messages = MessagesFake(resposta, erro)
    provider._client = SimpleNamespace(messages=messages)
    return messages


async def test_claude_usa_structured_output_nativo(config):
    provider = ClaudeProvider(config)
    assert provider.nome == "claude"
    messages = _mockar_claude(provider, _resposta_claude(RESPOSTA_JSON))

    comando = await provider.interpretar_comando("abre o spotify")

    formato = messages.kwargs["output_config"]["format"]
    assert formato == {"type": "json_schema", "schema": ESQUEMA_COMANDO}
    # Com o schema imposto pela API, o prompt e a personalidade pura.
    assert messages.kwargs["system"] == SYSTEM_PROMPT
    assert messages.kwargs["model"] == "claude-opus-5"
    assert messages.kwargs["messages"] == [
        {"role": "user", "content": "abre o spotify"}
    ]
    assert comando.acao == "abrir_app"
    assert comando.parametros == {"app": "Spotify"}


async def test_claude_limita_o_esforco_de_raciocinio(config):
    """O thinking adaptativo sai do mesmo teto de max_tokens da resposta."""
    provider = ClaudeProvider(config)
    messages = _mockar_claude(provider, _resposta_claude(RESPOSTA_JSON))

    await provider.interpretar_comando("oi")

    assert messages.kwargs["output_config"]["effort"] == "low"
    assert messages.kwargs["max_tokens"] == config.shogun_max_tokens


async def test_claude_sem_chave_falha_sem_chamar_api():
    provider = ClaudeProvider(Settings(_env_file=None, anthropic_api_key=""))
    assert not provider.configurado
    with pytest.raises(LLMIndisponivelError, match="ANTHROPIC_API_KEY"):
        await provider.interpretar_comando("oi")


async def test_claude_converte_erro_de_api_em_erro_do_dominio(config):
    provider = ClaudeProvider(config)
    _mockar_claude(provider, erro=anthropic.APIConnectionError(request=None))
    with pytest.raises(LLMIndisponivelError, match="Anthropic"):
        await provider.interpretar_comando("oi")


async def test_claude_recusa_do_modelo_vira_erro_do_dominio(config):
    provider = ClaudeProvider(config)
    _mockar_claude(
        provider,
        _resposta_claude(
            None,
            stop_reason="refusal",
            stop_details=SimpleNamespace(explanation="nao posso ajudar"),
        ),
    )
    with pytest.raises(LLMIndisponivelError, match="nao posso ajudar"):
        await provider.interpretar_comando("oi")


async def test_claude_resposta_truncada_vira_erro_do_dominio(config):
    provider = ClaudeProvider(config)
    _mockar_claude(provider, _resposta_claude(RESPOSTA_JSON, stop_reason="max_tokens"))
    with pytest.raises(LLMIndisponivelError, match="SHOGUN_MAX_TOKENS"):
        await provider.interpretar_comando("oi")


async def test_claude_sem_bloco_de_texto_vira_erro_do_dominio(config):
    provider = ClaudeProvider(config)
    _mockar_claude(provider, _resposta_claude(None))
    with pytest.raises(LLMIndisponivelError, match="sem conteudo|sem conte"):
        await provider.interpretar_comando("oi")


# --- Ollama ---------------------------------------------------------------

# Os testes usam httpx.MockTransport: o httpx real roda por baixo, entao
# status HTTP, raise_for_status e ConnectError se comportam como em producao.


def _ollama_ok(conteudo=RESPOSTA_JSON, done_reason="stop"):
    """Handler que devolve uma resposta bem formada do /api/chat."""
    capturado = {}

    def handler(request: httpx.Request) -> httpx.Response:
        capturado["url"] = str(request.url)
        capturado["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "hermes3:8b",
                "message": {"role": "assistant", "content": conteudo},
                "done": True,
                "done_reason": done_reason,
            },
        )

    return httpx.MockTransport(handler), capturado


def _ollama_erro(exc: Exception):
    def handler(request: httpx.Request) -> httpx.Response:
        raise exc

    return httpx.MockTransport(handler)


def _ollama_status(codigo: int, corpo: str):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(codigo, text=corpo)

    return httpx.MockTransport(handler)


async def test_ollama_usa_endpoint_nativo_com_schema_completo(config):
    transporte, capturado = _ollama_ok()
    provider = OllamaProvider(config, transport=transporte)
    assert provider.nome == "ollama"

    comando = await provider.interpretar_comando("abre o spotify")

    assert capturado["url"] == "http://localhost:11434/api/chat"
    corpo = capturado["body"]
    assert corpo["model"] == "hermes3:8b"
    assert corpo["stream"] is False
    # Schema completo, nao apenas {"format": "json"}: e isso que restringe a
    # decodificacao por gramatica em vez de so garantir JSON sintatico.
    assert corpo["format"] == ESQUEMA_COMANDO
    assert corpo["options"]["num_predict"] == config.shogun_max_tokens
    assert corpo["options"]["temperature"] == 0
    # A personalidade e a mesma dos outros provedores.
    sistema = corpo["messages"][0]["content"]
    assert sistema.startswith(SYSTEM_PROMPT)
    assert "resposta_falada" in sistema
    assert corpo["messages"][1] == {"role": "user", "content": "abre o spotify"}
    assert comando.acao == "abrir_app"
    assert comando.parametros == {"app": "Spotify"}


async def test_ollama_respeita_base_url_configurada():
    config = Settings(
        _env_file=None,
        ollama_base_url="http://192.168.0.10:11434/",  # barra final de proposito
        ollama_model="hermes3:70b",
    )
    transporte, capturado = _ollama_ok()

    await OllamaProvider(config, transport=transporte).interpretar_comando("oi")

    # A barra final nao pode virar // no caminho.
    assert capturado["url"] == "http://192.168.0.10:11434/api/chat"
    assert capturado["body"]["model"] == "hermes3:70b"


def test_ollama_nao_exige_credencial(config):
    """Modelo local nao tem chave: `configurado` nao pode depender de credencial."""
    assert OllamaProvider(config).configurado


async def test_ollama_fora_do_ar_vira_erro_do_dominio(config):
    transporte = _ollama_erro(httpx.ConnectError("connection refused"))
    provider = OllamaProvider(config, transport=transporte)

    with pytest.raises(LLMIndisponivelError, match="rodando"):
        await provider.interpretar_comando("oi")


async def test_ollama_timeout_vira_erro_do_dominio(config):
    transporte = _ollama_erro(httpx.ConnectTimeout("estourou"))
    provider = OllamaProvider(config, transport=transporte)

    with pytest.raises(LLMIndisponivelError, match="excedeu"):
        await provider.interpretar_comando("oi")


async def test_ollama_modelo_nao_baixado_vira_erro_do_dominio(config):
    """404 do Ollama normalmente e `ollama pull` que faltou."""
    provider = OllamaProvider(
        config, transport=_ollama_status(404, 'model "hermes3:8b" not found')
    )
    with pytest.raises(LLMIndisponivelError, match="404"):
        await provider.interpretar_comando("oi")


async def test_ollama_json_malformado_vira_erro_do_dominio(config):
    transporte, _ = _ollama_ok(conteudo="quase json, mas nao")
    provider = OllamaProvider(config, transport=transporte)

    with pytest.raises(LLMIndisponivelError, match="JSON"):
        await provider.interpretar_comando("oi")


async def test_ollama_json_fora_do_schema_vira_erro_do_dominio(config):
    """Modelo pequeno pode devolver JSON valido com acao inexistente."""
    transporte, _ = _ollama_ok(conteudo=json.dumps({"acao": "cozinhar"}))
    provider = OllamaProvider(config, transport=transporte)

    with pytest.raises(LLMIndisponivelError, match="formato"):
        await provider.interpretar_comando("oi")


async def test_ollama_resposta_truncada_vira_erro_do_dominio(config):
    transporte, _ = _ollama_ok(done_reason="length")
    provider = OllamaProvider(config, transport=transporte)

    with pytest.raises(LLMIndisponivelError, match="SHOGUN_MAX_TOKENS"):
        await provider.interpretar_comando("oi")


async def test_ollama_sem_conteudo_vira_erro_do_dominio(config):
    transporte, _ = _ollama_ok(conteudo="")
    provider = OllamaProvider(config, transport=transporte)

    with pytest.raises(LLMIndisponivelError, match="sem conteudo"):
        await provider.interpretar_comando("oi")


# --- Ollama + fallback (o cenario de uso local) ---------------------------


async def test_ollama_fora_do_ar_ativa_o_fallback(config, caplog):
    """Ollama desligado nao pode derrubar o comando — a nuvem assume."""
    local = OllamaProvider(config, transport=_ollama_erro(httpx.ConnectError("recusou")))
    nuvem = ProviderDeTeste("claude")

    comando = await FallbackLLMProvider(local, nuvem).interpretar_comando("oi")

    assert comando.resposta_falada == "resposta de claude"
    assert nuvem.chamado
    assert "ollama" in caplog.text.lower()


async def test_ollama_com_json_malformado_ativa_o_fallback(config):
    """O caso que motiva o fallback: modelo 8B devolvendo JSON inaproveitavel."""
    transporte, _ = _ollama_ok(conteudo="{acao: conversar,,}")
    local = OllamaProvider(config, transport=transporte)
    nuvem = ProviderDeTeste("deepseek")

    comando = await FallbackLLMProvider(local, nuvem).interpretar_comando("oi")

    assert comando.resposta_falada == "resposta de deepseek"
    assert nuvem.chamado


async def test_ollama_ok_nao_gasta_api_paga(config):
    """Caminho normal do uso local: o provedor pago nem e tocado."""
    transporte, _ = _ollama_ok()
    local = OllamaProvider(config, transport=transporte)
    nuvem = ProviderDeTeste("claude")

    comando = await FallbackLLMProvider(local, nuvem).interpretar_comando("oi")

    assert comando.acao == "abrir_app"
    assert not nuvem.chamado


# --- registro e factory --------------------------------------------------


def test_registro_expoe_os_quatro_provedores():
    assert set(PROVIDERS) == {"claude", "deepseek", "openai_mini", "ollama"}
    assert PROVIDERS["claude"] is ClaudeProvider


def test_todo_provedor_registrado_satisfaz_a_interface(config):
    for nome in PROVIDERS:
        provider = criar_provider(nome, config)
        assert isinstance(provider, LLMProvider)
        assert provider.nome == nome


def test_provedor_desconhecido_falha_com_mensagem_util(config):
    with pytest.raises(ProviderDesconhecidoError, match="Dispon"):
        criar_provider("gemini", config)


def test_sem_fallback_configurado_devolve_o_provedor_puro(config):
    provider = montar_provider(
        config.model_copy(update={"shogun_llm_provider": "deepseek"})
    )
    assert isinstance(provider, DeepSeekProvider)


def test_com_fallback_configurado_devolve_o_wrapper(config):
    provider = montar_provider(
        config.model_copy(
            update={
                "shogun_llm_provider": "claude",
                "shogun_llm_fallback_provider": "deepseek",
            }
        )
    )
    assert isinstance(provider, FallbackLLMProvider)
    assert provider.principal.nome == "claude"
    assert provider.reserva.nome == "deepseek"


def test_fallback_igual_ao_principal_e_ignorado(config):
    provider = montar_provider(
        config.model_copy(
            update={
                "shogun_llm_provider": "claude",
                "shogun_llm_fallback_provider": "claude",
            }
        )
    )
    assert isinstance(provider, ClaudeProvider)


# --- fallback automatico -------------------------------------------------


class ProviderDeTeste:
    def __init__(self, nome: str, erro: str | None = None):
        self.nome = nome
        self.erro = erro
        self.chamado = False

    @property
    def configurado(self) -> bool:
        return True

    async def interpretar_comando(self, texto: str) -> ComandoInterpretado:
        self.chamado = True
        if self.erro:
            raise LLMIndisponivelError(self.erro)
        return ComandoInterpretado(
            acao="conversar", parametros={}, resposta_falada=f"resposta de {self.nome}"
        )


async def test_principal_ok_nao_aciona_o_fallback():
    principal, reserva = ProviderDeTeste("claude"), ProviderDeTeste("deepseek")

    comando = await FallbackLLMProvider(principal, reserva).interpretar_comando("oi")

    assert comando.resposta_falada == "resposta de claude"
    assert not reserva.chamado


async def test_principal_falha_e_o_fallback_assume(caplog):
    principal = ProviderDeTeste("claude", erro="rate limit")
    reserva = ProviderDeTeste("deepseek")

    comando = await FallbackLLMProvider(principal, reserva).interpretar_comando("oi")

    assert comando.resposta_falada == "resposta de deepseek"
    assert reserva.chamado
    assert "rate limit" in caplog.text  # o motivo da troca fica no log


async def test_ambos_falham_e_o_erro_propaga_com_os_dois_motivos():
    principal = ProviderDeTeste("claude", erro="timeout")
    reserva = ProviderDeTeste("deepseek", erro="500")

    with pytest.raises(LLMIndisponivelError) as exc:
        await FallbackLLMProvider(principal, reserva).interpretar_comando("oi")

    assert "claude: timeout" in str(exc.value)
    assert "deepseek: 500" in str(exc.value)
    # O erro original continua encadeado para diagnostico.
    assert isinstance(exc.value.__cause__, LLMIndisponivelError)


async def test_fallback_cobre_timeout_do_provedor_real(config):
    """Integra provedor real (com HTTP mockado) e wrapper de fallback."""
    principal = DeepSeekProvider(config)
    _mockar(principal, erro=APITimeoutError(request=SimpleNamespace()))
    reserva = OpenAIMiniProvider(config)
    _mockar(reserva, _resposta_openai(RESPOSTA_JSON))

    comando = await FallbackLLMProvider(principal, reserva).interpretar_comando("oi")

    assert comando.acao == "abrir_app"
