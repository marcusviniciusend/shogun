"""Fixtures compartilhadas — nenhum teste toca em API real."""

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

# O servidor ainda não é empacotado; torna `app` importável a partir de server/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import Settings  # noqa: E402
from app.core.llm import ComandoInterpretado, LLMIndisponivelError  # noqa: E402
from app.db import Base, RepositorioConversas, criar_engine  # noqa: E402
from app.db.engine import sessionmaker_do_engine  # noqa: E402
from app.domain import Pendencia, PendenciasProvider, StatusAgente  # noqa: E402

TOKEN = "token-de-teste"


class LLMFake:
    """Provedor controlável: devolve `resposta` ou levanta `erro`."""

    def __init__(self, resposta: ComandoInterpretado | None = None, erro: str | None = None):
        self.nome = "fake"
        self.resposta = resposta or ComandoInterpretado(
            acao="conversar", parametros={}, resposta_falada="Olá, Marcus."
        )
        self.erro = erro
        self.chamadas: list[str] = []

    @property
    def configurado(self) -> bool:
        return True

    async def interpretar_comando(self, texto: str) -> ComandoInterpretado:
        self.chamadas.append(texto)
        if self.erro is not None:
            raise LLMIndisponivelError(self.erro)
        return self.resposta


def _pendencia(descricao: str, prioridade: int = 0, status=StatusAgente.PENDENTE):
    return Pendencia(
        agente_id="a1",
        agente_nome="Contratos",
        status=status,
        descricao=descricao,
        timestamp=datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc),
        prioridade=prioridade,
    )


class PendenciasFake(PendenciasProvider):
    """Implementa o contrato real do agente-contratos (síncrono, sem limite)."""

    def __init__(self, pendencias=None):
        self.pendencias = (
            pendencias
            if pendencias is not None
            else [
                _pendencia("Assinar contrato", prioridade=5),
                _pendencia("Ligar pro contador"),
            ]
        )

    def get_pendencias_agentes(self):
        return list(self.pendencias)

    def get_status_agente(self, agente_id: str) -> StatusAgente:
        return StatusAgente.PENDENTE


# --- Banco de dados --------------------------------------------------------
#
# SQLite em memoria, um por teste. Nenhum teste toca o banco real: a URL de
# producao nem chega a ser aberta, porque `get_db` e sobrescrito.


@pytest.fixture
def db_engine():
    engine = criar_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db(db_engine):
    """Sessao do SQLAlchemy ligada ao banco em memoria do teste."""
    sessao = sessionmaker_do_engine(db_engine)()
    try:
        yield sessao
    finally:
        sessao.close()


@pytest.fixture
def repo(db) -> RepositorioConversas:
    return RepositorioConversas(db)


@pytest.fixture
def settings_teste() -> Settings:
    # _env_file=None isola os testes de um .env real na máquina do desenvolvedor.
    return Settings(_env_file=None, shogun_auth_token=TOKEN)


@pytest.fixture
def llm() -> LLMFake:
    return LLMFake()


@pytest.fixture
def client(settings_teste, llm, db_engine):
    """TestClient com todas as dependências externas sobrescritas."""
    from fastapi.testclient import TestClient

    from app.core.llm import get_llm_provider
    from app.core.pendencias import get_pendencias_provider
    from app.core.security import get_settings
    from app.db import get_db
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
        # lambda, e nao a classe: FastAPI inspecionaria o __init__ como dependência.
        get_pendencias_provider: lambda: PendenciasFake(),
        get_db: get_db_teste,
    }
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def corpo() -> dict[str, str]:
    return {"session_id": "s1", "text": "bom dia", "client": "desktop"}
