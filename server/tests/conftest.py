"""Fixtures compartilhadas — nenhum teste toca em API real."""

import sys
from pathlib import Path

import pytest

# O servidor ainda não é empacotado; torna `app` importável a partir de server/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import Settings  # noqa: E402
from app.core.llm import ComandoInterpretado, LLMIndisponivelError  # noqa: E402
from app.core.pendencias import Pendencia  # noqa: E402

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


class PendenciasFake:
    disponivel = True

    async def listar_pendencias(self, limite: int = 10):
        return [
            Pendencia(titulo="Assinar contrato", prazo="sexta"),
            Pendencia(titulo="Ligar pro contador"),
        ][:limite]


@pytest.fixture
def settings_teste() -> Settings:
    # _env_file=None isola os testes de um .env real na máquina do desenvolvedor.
    return Settings(_env_file=None, shogun_auth_token=TOKEN)


@pytest.fixture
def llm() -> LLMFake:
    return LLMFake()


@pytest.fixture
def client(settings_teste, llm):
    """TestClient com todas as dependências externas sobrescritas."""
    from fastapi.testclient import TestClient

    from app.core.llm import get_llm_provider
    from app.core.pendencias import get_pendencias_provider
    from app.core.security import get_settings
    from app.main import app

    app.dependency_overrides = {
        get_settings: lambda: settings_teste,
        get_llm_provider: lambda: llm,
        get_pendencias_provider: PendenciasFake,
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
