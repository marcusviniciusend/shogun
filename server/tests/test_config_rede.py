"""Exposição de rede: bind aberto exige token; bind local, não.

A regra vale antes de o servidor escutar — o objetivo é não subir aberto, não
avisar depois que já subiu.
"""

import pytest
from fastapi import FastAPI

from app.core.config import ConfiguracaoInseguraError, Settings


def _settings(**kwargs) -> Settings:
    # _env_file=None isola o teste de um .env real na máquina do desenvolvedor.
    return Settings(_env_file=None, **kwargs)


@pytest.mark.parametrize("host", ["0.0.0.0", "100.101.102.103", "::", "192.168.0.10"])
def test_bind_aberto_sem_token_recusa_subir(host):
    settings = _settings(shogun_host=host, shogun_auth_token="")

    assert settings.exposto_na_rede is True
    with pytest.raises(ConfiguracaoInseguraError) as erro:
        settings.validar_exposicao()

    # A mensagem precisa dizer o que fazer, não só que deu errado.
    assert "SHOGUN_AUTH_TOKEN" in str(erro.value)
    assert "127.0.0.1" in str(erro.value)


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1", "LocalHost"])
def test_bind_local_sem_token_e_permitido(host):
    """Desenvolvimento local não precisa de token: ninguém de fora alcança."""
    settings = _settings(shogun_host=host, shogun_auth_token="")

    assert settings.exposto_na_rede is False
    settings.validar_exposicao()  # não levanta


def test_bind_aberto_com_token_e_permitido():
    settings = _settings(shogun_host="0.0.0.0", shogun_auth_token="segredo")

    assert settings.exposto_na_rede is True
    settings.validar_exposicao()  # não levanta


def test_lifespan_recusa_subir_com_configuracao_insegura(monkeypatch):
    """A recusa vale no startup — inclusive via `uvicorn app.main:app`."""
    from fastapi.testclient import TestClient

    from app import main

    monkeypatch.setattr(
        main.settings, "shogun_host", "0.0.0.0", raising=False
    )
    monkeypatch.setattr(main.settings, "shogun_auth_token", "", raising=False)

    with pytest.raises(ConfiguracaoInseguraError):
        with TestClient(main.app):
            pass


def test_lifespan_sobe_com_token(monkeypatch):
    from fastapi.testclient import TestClient

    from app import main

    monkeypatch.setattr(main.settings, "shogun_host", "0.0.0.0", raising=False)
    monkeypatch.setattr(main.settings, "shogun_auth_token", "segredo", raising=False)

    with TestClient(main.app) as client:
        assert client.get("/health").status_code == 200


# --- CORS -------------------------------------------------------------------


def test_origens_vazias_nao_registram_o_middleware():
    """Sem origem configurada, CORS não entra: os clientes atuais não usam."""
    assert _settings(shogun_allowed_origins="").allowed_origins == []


def test_origens_sao_separadas_por_virgula_e_sem_espacos():
    settings = _settings(
        shogun_allowed_origins="http://100.101.102.103:8000, http://localhost:1420 ,"
    )

    assert settings.allowed_origins == [
        "http://100.101.102.103:8000",
        "http://localhost:1420",
    ]


def test_middleware_de_cors_responde_ao_preflight():
    origem = "http://100.101.102.103:8000"
    app = FastAPI()

    from fastapi.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_settings(shogun_allowed_origins=origem).allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    from fastapi.testclient import TestClient

    resposta = TestClient(app).options(
        "/health",
        headers={
            "Origin": origem,
            "Access-Control-Request-Method": "POST",
        },
    )

    assert resposta.status_code == 200
    assert resposta.headers["access-control-allow-origin"] == origem
