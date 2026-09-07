"""Testes do GET /pendencias — consulta direta, sem LLM e sem rede."""

from datetime import datetime, timezone

from app.core.pendencias import get_pendencias_provider
from app.domain import StatusAgente

from .conftest import PendenciasFake, _pendencia


def test_sem_credenciais_retorna_401(client):
    assert client.get("/pendencias").status_code == 401


def test_token_invalido_retorna_401(client):
    resposta = client.get(
        "/pendencias", headers={"Authorization": "Bearer errado"}
    )
    assert resposta.status_code == 401


def test_lista_pendencias_com_o_shape_do_dominio(client, auth):
    resposta = client.get("/pendencias", headers=auth)

    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["total"] == 2
    assert len(dados["pendencias"]) == 2
    primeira = dados["pendencias"][0]
    # Serializacao direta dos modelos de dominio, sem conversao manual.
    assert primeira["agente_id"] == "a1"
    assert primeira["agente_nome"] == "Contratos"
    assert primeira["status"] == "pendente"
    assert primeira["descricao"] == "Assinar contrato"
    assert primeira["prioridade"] == 5
    assert "timestamp" in primeira


def test_ordena_por_urgencia_como_a_fala_do_comando(client, auth):
    """Prioridade decrescente e, no empate, timestamp mais antigo primeiro."""
    from app.main import app

    antiga = _pendencia("Empate antigo", prioridade=1)
    recente = antiga.model_copy(
        update={
            "descricao": "Empate recente",
            "timestamp": datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc),
        }
    )
    urgente = _pendencia("Mais urgente", prioridade=9)
    app.dependency_overrides[get_pendencias_provider] = lambda: PendenciasFake(
        [recente, antiga, urgente]
    )

    dados = client.get("/pendencias", headers=auth).json()

    assert [p["descricao"] for p in dados["pendencias"]] == [
        "Mais urgente",
        "Empate antigo",
        "Empate recente",
    ]


def test_sem_pendencias_devolve_lista_vazia(client, auth):
    from app.main import app

    app.dependency_overrides[get_pendencias_provider] = lambda: PendenciasFake([])

    dados = client.get("/pendencias", headers=auth).json()

    assert dados == {"total": 0, "pendencias": []}


def test_falha_do_provedor_vira_503(client, auth):
    from app.main import app

    class ProvedorQuebrado(PendenciasFake):
        def get_pendencias_agentes(self):
            raise RuntimeError("API do Maestri fora")

    app.dependency_overrides[get_pendencias_provider] = lambda: ProvedorQuebrado()

    resposta = client.get("/pendencias", headers=auth)

    assert resposta.status_code == 503
    assert "pendencias" in resposta.json()["detail"].lower()


def test_nao_passa_pelo_llm(client, auth, llm):
    """A razao de existir da rota: nenhuma chamada ao provedor de LLM."""
    resposta = client.get("/pendencias", headers=auth)

    assert resposta.status_code == 200
    assert llm.chamadas == []


def test_provedor_sincrono_roda_fora_do_event_loop(client, auth):
    """get_pendencias_agentes() e sincrono e vai para a threadpool."""
    import threading

    from app.main import app

    threads: list[str] = []

    class Espiao(PendenciasFake):
        def get_pendencias_agentes(self):
            threads.append(threading.current_thread().name)
            return super().get_pendencias_agentes()

    app.dependency_overrides[get_pendencias_provider] = lambda: Espiao()

    assert client.get("/pendencias", headers=auth).status_code == 200
    assert threads and all("anyio" in nome.lower() for nome in threads), threads


def test_status_travado_sai_serializado_pelo_valor(client, auth):
    from app.main import app

    app.dependency_overrides[get_pendencias_provider] = lambda: PendenciasFake(
        [_pendencia("Deploy parado", status=StatusAgente.TRAVADO)]
    )

    dados = client.get("/pendencias", headers=auth).json()

    assert dados["pendencias"][0]["status"] == "travado"
