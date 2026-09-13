"""Testes do rastreamento de consumo: captura, persistência, preços e rota.

Todos os cálculos são validados com dados sintéticos de uso conhecido —
nenhum provedor real é chamado.
"""

import json
from datetime import datetime
from types import SimpleNamespace

import httpx
import pytest

from app.core.config import Settings
from app.core.llm import (
    ClaudeProvider,
    ComandoInterpretado,
    DeepSeekProvider,
    OllamaProvider,
    UsoTokens,
    parsear_comando,
)
from app.core.llm.precos import PRECOS, custo_usd

RESPOSTA_JSON = json.dumps(
    {
        "acao": "conversar",
        "parametros": {"app": None, "limite": None},
        "resposta_falada": "Olá, Marcus.",
    }
)


@pytest.fixture
def config() -> Settings:
    return Settings(
        _env_file=None,
        anthropic_api_key="ant-x",
        deepseek_api_key="ds-x",
        ollama_model="hermes3:8b",
    )


# --- tabela de preços -----------------------------------------------------


def test_tabela_cobre_os_quatro_provedores():
    assert set(PRECOS) == {"claude", "deepseek", "openai_mini", "ollama"}


def test_custo_claude_em_volume_redondo():
    # 1M de input a US$ 5 + 1M de output a US$ 25 (Opus, o modelo default).
    assert custo_usd("claude", 1_000_000, 1_000_000) == pytest.approx(30.0)


def test_custo_proporcional_ao_volume():
    # 100k input + 50k output no gpt-4o-mini: 0.1*0.15 + 0.05*0.60.
    assert custo_usd("openai_mini", 100_000, 50_000) == pytest.approx(0.045)


def test_ollama_custa_zero_sempre():
    assert custo_usd("ollama", 5_000_000, 5_000_000) == 0.0


def test_provedor_fora_da_tabela_custa_zero():
    # `deterministico` e fakes de teste não têm preço cadastrado.
    assert custo_usd("deterministico", 1_000_000, 1_000_000) == 0.0


# --- captura nos provedores ----------------------------------------------


async def test_claude_captura_usage(config):
    provider = ClaudeProvider(config)
    resposta = SimpleNamespace(
        stop_reason="end_turn",
        content=[SimpleNamespace(type="text", text=RESPOSTA_JSON)],
        usage=SimpleNamespace(input_tokens=120, output_tokens=45),
    )

    async def create(**kwargs):
        return resposta

    provider._client = SimpleNamespace(
        messages=SimpleNamespace(create=create)
    )

    comando = await provider.interpretar_comando("bom dia")
    assert comando.uso == UsoTokens(provider="claude", input_tokens=120, output_tokens=45)


async def test_openai_compat_captura_usage(config):
    provider = DeepSeekProvider(config)
    resposta = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=RESPOSTA_JSON, refusal=None),
                finish_reason="stop",
            )
        ],
        usage=SimpleNamespace(prompt_tokens=200, completion_tokens=80),
    )

    async def create(**kwargs):
        return resposta

    provider._client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )

    comando = await provider.interpretar_comando("bom dia")
    assert comando.uso == UsoTokens(
        provider="deepseek", input_tokens=200, output_tokens=80
    )


async def test_openai_compat_sem_usage_nao_derruba(config):
    provider = DeepSeekProvider(config)
    resposta = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=RESPOSTA_JSON, refusal=None),
                finish_reason="stop",
            )
        ],
        usage=None,
    )

    async def create(**kwargs):
        return resposta

    provider._client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )

    comando = await provider.interpretar_comando("bom dia")
    assert comando.uso is None


async def test_ollama_captura_contagens_nativas(config):
    corpo = {
        "message": {"role": "assistant", "content": RESPOSTA_JSON},
        "done_reason": "stop",
        "prompt_eval_count": 310,
        "eval_count": 55,
    }
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json=corpo)
    )
    provider = OllamaProvider(config, transport=transport)

    comando = await provider.interpretar_comando("bom dia")
    assert comando.uso == UsoTokens(
        provider="ollama", input_tokens=310, output_tokens=55
    )


async def test_ollama_sem_prompt_eval_count_vira_zero(config):
    # O Ollama omite prompt_eval_count quando o prompt veio inteiro do cache.
    corpo = {
        "message": {"role": "assistant", "content": RESPOSTA_JSON},
        "done_reason": "stop",
        "eval_count": 20,
    }
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json=corpo)
    )
    provider = OllamaProvider(config, transport=transport)

    comando = await provider.interpretar_comando("bom dia")
    assert comando.uso == UsoTokens(provider="ollama", input_tokens=0, output_tokens=20)


def test_modelo_nao_injeta_uso_pelo_json():
    fabricado = json.loads(RESPOSTA_JSON)
    fabricado["uso"] = {"provider": "claude", "input_tokens": 1, "output_tokens": 1}
    comando = parsear_comando(json.dumps(fabricado))
    assert comando.uso is None


# --- persistência ---------------------------------------------------------


def _semear_uso(db, repo, provider: str, entrada: int, saida: int, momento: datetime):
    """Uma fala do assistente com uso conhecido, datada artificialmente."""
    sessao = repo.criar_sessao()
    mensagem = repo.registrar_assistente(sessao.id, "resposta")
    uso = repo.registrar_uso(mensagem.id, provider, entrada, saida)
    uso.created_at = momento
    db.commit()
    return uso


def test_consumo_agrega_por_provider(db, repo):
    dia = datetime(2026, 9, 1, 12, 0)
    _semear_uso(db, repo, "claude", 100, 50, dia)
    _semear_uso(db, repo, "claude", 200, 70, dia)
    _semear_uso(db, repo, "ollama", 1000, 400, dia)

    linhas = {l.provider: l for l in repo.consumo_por_provider()}
    assert linhas["claude"].mensagens == 2
    assert linhas["claude"].input_tokens == 300
    assert linhas["claude"].output_tokens == 120
    assert linhas["ollama"].input_tokens == 1000


def test_consumo_filtra_por_periodo(db, repo):
    _semear_uso(db, repo, "claude", 100, 10, datetime(2026, 8, 1))
    _semear_uso(db, repo, "claude", 200, 20, datetime(2026, 9, 1))
    _semear_uso(db, repo, "claude", 400, 40, datetime(2026, 9, 15))

    # inicio inclusivo, fim exclusivo.
    linhas = repo.consumo_por_provider(
        inicio=datetime(2026, 9, 1), fim=datetime(2026, 9, 15)
    )
    assert len(linhas) == 1
    assert linhas[0].input_tokens == 200

    tudo = repo.consumo_por_provider()
    assert tudo[0].input_tokens == 700


def test_consumo_sem_dados_e_lista_vazia(repo):
    assert repo.consumo_por_provider() == []


# --- rota POST /comando grava o uso --------------------------------------


def test_comando_persiste_uso_do_provedor(client, llm, auth, corpo, repo):
    llm.resposta = ComandoInterpretado(
        acao="conversar",
        parametros={},
        resposta_falada="Olá, Marcus.",
        uso=UsoTokens(provider="claude", input_tokens=42, output_tokens=7),
    )

    assert client.post("/comando", json=corpo, headers=auth).status_code == 200

    linhas = repo.consumo_por_provider()
    assert len(linhas) == 1
    assert linhas[0] == ("claude", 1, 42, 7)


def test_comando_sem_uso_nao_grava_nada(client, auth, corpo, repo):
    # O LLMFake default responde sem uso — como o provedor deterministico.
    assert client.post("/comando", json=corpo, headers=auth).status_code == 200
    assert repo.consumo_por_provider() == []


# --- rota GET /consumo ----------------------------------------------------


def test_consumo_exige_token(client):
    assert client.get("/consumo").status_code == 401


def test_consumo_vazio(client, auth):
    dados = client.get("/consumo", headers=auth).json()
    assert dados["total_input_tokens"] == 0
    assert dados["custo_real_usd"] == 0.0
    assert dados["por_provider"] == []
    # O comparativo existe mesmo sem consumo: um item por provedor da tabela.
    assert {c["provider"] for c in dados["comparativo"]} == set(PRECOS)


def test_consumo_calcula_custo_real_e_comparativo(client, auth, db, repo):
    dia = datetime(2026, 9, 1, 12, 0)
    # Volumes redondos para conferir o cálculo de cabeça.
    _semear_uso(db, repo, "claude", 1_000_000, 100_000, dia)
    _semear_uso(db, repo, "ollama", 2_000_000, 500_000, dia)

    dados = client.get("/consumo", headers=auth).json()

    assert dados["total_input_tokens"] == 3_000_000
    assert dados["total_output_tokens"] == 600_000

    # Custo real: claude (Opus) 1M*5 + 0.1M*25 = 7.5; ollama = 0.
    assert dados["custo_real_usd"] == pytest.approx(7.5)

    por_provider = {p["provider"]: p for p in dados["por_provider"]}
    assert por_provider["claude"]["custo_usd"] == pytest.approx(7.5)
    assert por_provider["claude"]["mensagens"] == 1
    assert por_provider["ollama"]["custo_usd"] == 0.0

    # Comparativo aplica o volume TOTAL (3M in, 0.6M out) a cada tabela:
    comparativo = {c["provider"]: c["custo_usd"] for c in dados["comparativo"]}
    assert comparativo["claude"] == pytest.approx(3 * 5.0 + 0.6 * 25.0)
    assert comparativo["deepseek"] == pytest.approx(3 * 0.28 + 0.6 * 0.42)
    assert comparativo["openai_mini"] == pytest.approx(3 * 0.15 + 0.6 * 0.60)
    assert comparativo["ollama"] == 0.0


def test_consumo_respeita_o_periodo(client, auth, db, repo):
    _semear_uso(db, repo, "claude", 100, 10, datetime(2026, 8, 1))
    _semear_uso(db, repo, "claude", 200, 20, datetime(2026, 9, 1))

    dados = client.get(
        "/consumo",
        headers=auth,
        params={"inicio": "2026-08-15T00:00:00"},
    ).json()
    assert dados["total_input_tokens"] == 200

    dados = client.get(
        "/consumo",
        headers=auth,
        params={"fim": "2026-08-15T00:00:00"},
    ).json()
    assert dados["total_input_tokens"] == 100


def test_consumo_normaliza_data_com_fuso(client, auth, db, repo):
    _semear_uso(db, repo, "claude", 100, 10, datetime(2026, 9, 1, 12, 0))

    # 09:01 em UTC-3 = 12:01 UTC: com a normalização, o registro de 12:00 UTC
    # fica FORA do corte; sem ela (comparação ingênua), ficaria dentro.
    dados = client.get(
        "/consumo",
        headers=auth,
        params={"inicio": "2026-09-01T09:01:00-03:00"},
    ).json()
    assert dados["total_input_tokens"] == 0


# --- taxa de acionamento do fallback --------------------------------------
#
# O bloco `fallback` de /consumo deriva do mesmo agregado por provedor. O que
# estes testes protegem não é a divisão — é *quando ela se recusa a responder*.


def _configurar_llm(client, settings_teste, principal: str, reserva: str = ""):
    """Troca principal/reserva do ambiente sem recriar o TestClient.

    A rota lê a configuração por `get_settings`, já sobrescrito pelo `client`;
    aqui só reapontamos o override para uma `Settings` nova. `require_auth`
    depende do mesmo objeto, então o token precisa continuar valendo.
    """
    from app.core.security import get_settings
    from app.main import app

    nova = settings_teste.model_copy(
        update={
            "shogun_llm_provider": principal,
            "shogun_llm_fallback_provider": reserva,
        }
    )
    app.dependency_overrides[get_settings] = lambda: nova
    return nova


def _fallback(client, auth, **params):
    return client.get("/consumo", headers=auth, params=params).json()["fallback"]


def test_fallback_calcula_a_taxa_do_par_configurado(
    client, auth, db, repo, settings_teste
):
    _configurar_llm(client, settings_teste, "claude", "ollama")
    dia = datetime(2026, 9, 1, 12, 0)
    for _ in range(3):
        _semear_uso(db, repo, "claude", 100, 10, dia)
    _semear_uso(db, repo, "ollama", 100, 10, dia)

    bloco = _fallback(client, auth)

    assert bloco["principal_configurado"] == "claude"
    assert bloco["reserva_configurada"] == "ollama"
    assert bloco["mensagens_principal"] == 3
    assert bloco["mensagens_reserva"] == 1
    assert bloco["mensagens_outros"] == 0
    # 1 de 4 mensagens saiu pelo reserva.
    assert bloco["taxa"] == pytest.approx(0.25)
    assert bloco["motivo_sem_taxa"] is None


def test_fallback_nunca_acionado_e_taxa_zero_e_nao_ausencia_de_taxa(
    client, auth, db, repo, settings_teste
):
    # Distinção que importa: com o par registrando uso, zero acionamentos é uma
    # medida (0.0), não um "não sei" (None).
    _configurar_llm(client, settings_teste, "claude", "ollama")
    _semear_uso(db, repo, "claude", 100, 10, datetime(2026, 9, 1))

    bloco = _fallback(client, auth)
    assert bloco["taxa"] == 0.0
    assert bloco["motivo_sem_taxa"] is None


def test_fallback_sem_reserva_configurada_nao_inventa_taxa(
    client, auth, db, repo, settings_teste
):
    _configurar_llm(client, settings_teste, "claude", "")
    _semear_uso(db, repo, "claude", 100, 10, datetime(2026, 9, 1))

    bloco = _fallback(client, auth)
    assert bloco["reserva_configurada"] is None
    assert bloco["taxa"] is None
    assert bloco["motivo_sem_taxa"] == "sem_reserva_configurada"


def test_fallback_reserva_igual_ao_principal_e_tratada_como_ausente(
    client, auth, settings_teste
):
    # Mesma regra de `montar_provider`: nesse caso nem se monta um
    # FallbackLLMProvider, então não existe reserva para medir.
    _configurar_llm(client, settings_teste, "claude", "claude")

    bloco = _fallback(client, auth)
    assert bloco["reserva_configurada"] is None
    assert bloco["motivo_sem_taxa"] == "sem_reserva_configurada"


def test_fallback_sem_mensagens_do_par_no_periodo_nao_divide_por_zero(
    client, auth, db, repo, settings_teste
):
    _configurar_llm(client, settings_teste, "claude", "ollama")
    _semear_uso(db, repo, "deepseek", 100, 10, datetime(2026, 9, 1))

    bloco = _fallback(client, auth)
    assert bloco["mensagens_outros"] == 1
    assert bloco["taxa"] is None
    assert bloco["motivo_sem_taxa"] == "sem_mensagens_do_par"


def test_fallback_com_provedor_que_nao_grava_uso_se_recusa_a_responder(
    client, auth, db, repo, settings_teste
):
    # `deterministico` nunca escreve em messages_uso — é o fallback final que
    # sempre responde e some do banco. Zero linhas dele NÃO é zero
    # acionamentos, então a taxa não pode sair 0.0 com cara de medida.
    _configurar_llm(client, settings_teste, "claude", "deterministico")
    _semear_uso(db, repo, "claude", 100, 10, datetime(2026, 9, 1))

    bloco = _fallback(client, auth)
    assert bloco["mensagens_reserva"] == 0
    assert bloco["taxa"] is None
    assert bloco["motivo_sem_taxa"] == "provedor_nao_registra_uso"


def test_fallback_delata_mudanca_de_configuracao_em_mensagens_outros(
    client, auth, db, repo, settings_teste
):
    # A armadilha da janela: o principal de hoje é `ollama`, mas o período
    # consultado tem mensagens de `claude` e `deepseek`, que não são nem o
    # principal nem o reserva de agora. A resposta não finge que sempre foi
    # assim — conta essas mensagens à parte.
    _configurar_llm(client, settings_teste, "ollama", "deepseek")
    dia = datetime(2026, 9, 1, 12, 0)
    _semear_uso(db, repo, "ollama", 100, 10, dia)
    _semear_uso(db, repo, "deepseek", 100, 10, dia)
    _semear_uso(db, repo, "claude", 100, 10, dia)
    _semear_uso(db, repo, "openai_mini", 100, 10, dia)

    bloco = _fallback(client, auth)
    assert bloco["mensagens_principal"] == 1
    assert bloco["mensagens_reserva"] == 1
    # claude e openai_mini: prova de que a configuração já foi outra.
    assert bloco["mensagens_outros"] == 2
    # A taxa segue sendo do par de hoje — descritiva, não histórica.
    assert bloco["taxa"] == pytest.approx(0.5)


def test_fallback_respeita_a_janela_consultada(client, auth, db, repo, settings_teste):
    _configurar_llm(client, settings_teste, "claude", "ollama")
    _semear_uso(db, repo, "ollama", 100, 10, datetime(2026, 8, 1))
    _semear_uso(db, repo, "claude", 100, 10, datetime(2026, 9, 1))

    # Janela só de agosto: o reserva atendeu tudo.
    assert _fallback(client, auth, fim="2026-08-15T00:00:00")["taxa"] == 1.0
    # Janela só de setembro: o principal atendeu tudo.
    assert _fallback(client, auth, inicio="2026-08-15T00:00:00")["taxa"] == 0.0


def test_provedores_sem_uso_esta_em_dia():
    """Provedor novo que não grava `UsoTokens` precisa entrar na lista.

    Mesmo espírito de `test_paridade_contratos`: o que não pode acontecer é a
    lista silenciosamente desatualizar e a taxa passar a mentir. Aqui o sinal é
    o código-fonte da classe citar `UsoTokens` — quem preenche uso, cita.
    """
    import inspect

    from app.core.llm import PROVEDORES_SEM_REGISTRO_DE_USO, PROVIDERS

    assert PROVEDORES_SEM_REGISTRO_DE_USO <= set(PROVIDERS)
    for nome, classe in PROVIDERS.items():
        grava = "UsoTokens" in inspect.getsource(inspect.getmodule(classe))
        assert grava is (nome not in PROVEDORES_SEM_REGISTRO_DE_USO), nome
