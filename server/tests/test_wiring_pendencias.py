"""O wiring default de pendências: rotas lendo do banco de verdade.

Diferente dos outros testes de rota, aqui `get_pendencias_provider` NÃO é
sobrescrito: o client usa o wiring real (provider persistente sobre a sessão do
request), com apenas `get_db` apontado para o SQLite em memória do teste. É o
teste de que /comando e GET /pendencias funcionam com o default novo.
"""

from datetime import datetime, timezone

import pytest

from app.core.llm import ComandoInterpretado
from app.db import RepositorioPendencias
from app.domain import Pendencia, StatusAgente

from .conftest import TOKEN

AGORA = datetime(2026, 9, 7, 15, 0, tzinfo=timezone.utc)


@pytest.fixture
def client_com_banco(settings_teste, llm, db_engine):
    """TestClient SEM override de get_pendencias_provider — wiring real."""
    from fastapi.testclient import TestClient

    from app.core.llm import get_llm_provider
    from app.core.security import get_settings
    from app.db import get_db
    from app.db.engine import sessionmaker_do_engine
    from app.main import app

    fabrica = sessionmaker_do_engine(db_engine)

    def get_db_teste():
        sessao = fabrica()
        try:
            yield sessao
        finally:
            sessao.close()

    app.dependency_overrides = {
        get_settings: lambda: settings_teste,
        get_llm_provider: lambda: llm,
        get_db: get_db_teste,
    }
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def semear(db_engine):
    """Grava pendências direto pelo repositório, como o orquestrador faria."""
    from app.db.engine import sessionmaker_do_engine

    sessao = sessionmaker_do_engine(db_engine)()
    repo = RepositorioPendencias(sessao)
    repo.registrar(
        Pendencia(
            agente_id="a1",
            agente_nome="Contratos",
            status=StatusAgente.PENDENTE,
            descricao="Assinar contrato",
            timestamp=AGORA,
            prioridade=5,
        )
    )
    repo.registrar(
        Pendencia(
            agente_id="a2",
            agente_nome="Backend",
            status=StatusAgente.TRAVADO,
            descricao="Deploy parado",
            timestamp=AGORA,
            prioridade=1,
        )
    )
    sessao.close()


@pytest.fixture
def auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}


def test_get_pendencias_le_do_banco(client_com_banco, semear, auth):
    dados = client_com_banco.get("/pendencias", headers=auth).json()

    assert dados["total"] == 2
    assert [p["descricao"] for p in dados["pendencias"]] == [
        "Assinar contrato",
        "Deploy parado",
    ]


def test_get_pendencias_sem_nada_no_banco(client_com_banco, auth):
    dados = client_com_banco.get("/pendencias", headers=auth).json()
    assert dados == {"total": 0, "pendencias": []}


def test_comando_consultar_pendencias_le_do_banco(client_com_banco, semear, auth, llm):
    llm.resposta = ComandoInterpretado(
        acao="consultar_pendencias", parametros={}, resposta_falada="ok"
    )

    corpo = {"session_id": None, "text": "o que ta pendente?", "client": "desktop"}
    dados = client_com_banco.post("/comando", json=corpo, headers=auth).json()

    assert "Você tem 2 pendências" in dados["text"]
    # A mais urgente primeiro, e o status crítico aparece na fala.
    assert dados["text"].index("Assinar contrato") < dados["text"].index("Deploy parado")
    assert "Deploy parado (Backend, travado)" in dados["text"]
    assert dados["actions"][0]["detail"] == "2 pendências"


def test_escrita_pelo_provider_aparece_nas_rotas(client_com_banco, db_engine, auth):
    """O caminho completo: orquestrador escreve pelo provider persistente e as
    duas rotas leem — nada fica preso em memória de instância."""
    from app.db.engine import sessionmaker_do_engine
    from app.domain import ShogunOrquestradorProvider

    sessao = sessionmaker_do_engine(db_engine)()
    escritor = ShogunOrquestradorProvider(repositorio=RepositorioPendencias(sessao))
    escritor.registrar_pendencia(
        "a1", "Contratos", "Escrita pelo provider", timestamp=AGORA
    )
    sessao.close()

    dados = client_com_banco.get("/pendencias", headers=auth).json()
    assert dados["total"] == 1
    assert dados["pendencias"][0]["descricao"] == "Escrita pelo provider"
