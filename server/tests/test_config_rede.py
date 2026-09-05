"""Exposição de rede: bind aberto exige token; bind local, não.

A regra vale antes de o servidor escutar — o objetivo é não subir aberto, não
avisar depois que já subiu.
"""

import pytest
from fastapi import FastAPI

from app.core.config import ConfiguracaoInseguraError, Settings
from app.core.rede import BindEfetivo, descobrir_bind


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


# --- Bind real, e nao apenas SHOGUN_HOST ------------------------------------
#
# `uvicorn --host 0.0.0.0` ignora SHOGUN_HOST. A validação lê o bind que o
# uvicorn recebeu, então precisa ser testada contra as duas fontes.


class _ConfigFalsa:
    """Imita o `uvicorn.Config`: host, port, uds e fd juntos."""

    def __init__(self, host="0.0.0.0", uds=None, fd=None):
        self.host = host
        self.port = 8000
        self.uds = uds
        self.fd = fd


class _LifespanFalso:
    """Imita o `LifespanOn`, que é o frame de onde o bind é lido.

    Chamar `descobrir_bind` de dentro de um método desta classe reproduz a
    pilha real: um frame com `self.config` acima do código da aplicação.
    """

    def __init__(self, config):
        self.config = config

    def rodar(self, host_configurado):
        return descobrir_bind(host_configurado)


def test_fora_do_uvicorn_cai_para_shogun_host():
    bind = descobrir_bind("127.0.0.1")

    assert bind == BindEfetivo("127.0.0.1", "SHOGUN_HOST")


def test_host_do_uvicorn_vence_shogun_host():
    """A brecha: --host 0.0.0.0 com SHOGUN_HOST=127.0.0.1 no .env."""
    bind = _LifespanFalso(_ConfigFalsa(host="0.0.0.0")).rodar("127.0.0.1")

    assert bind == BindEfetivo("0.0.0.0", "uvicorn --host")

    with pytest.raises(ConfiguracaoInseguraError) as erro:
        _settings(shogun_host="127.0.0.1", shogun_auth_token="").validar_exposicao(bind)

    assert "uvicorn --host" in str(erro.value)


def test_uvicorn_local_com_shogun_host_aberto_e_permitido():
    """O inverso: quem escuta local de verdade não precisa de token."""
    bind = _LifespanFalso(_ConfigFalsa(host="127.0.0.1")).rodar("0.0.0.0")

    assert bind == BindEfetivo("127.0.0.1", "uvicorn --host")
    _settings(shogun_host="0.0.0.0", shogun_auth_token="").validar_exposicao(bind)


def test_socket_de_arquivo_conta_como_local():
    bind = _LifespanFalso(_ConfigFalsa(host="0.0.0.0", uds="/tmp/shogun.sock")).rodar(
        "0.0.0.0"
    )

    assert bind.host == "127.0.0.1"
    _settings(shogun_auth_token="").validar_exposicao(bind)  # não levanta


def test_descritor_herdado_e_tratado_como_exposto():
    """Com --fd não dá para saber onde já se escuta; erra para o lado seguro."""
    bind = _LifespanFalso(_ConfigFalsa(host="127.0.0.1", fd=3)).rodar("127.0.0.1")

    with pytest.raises(ConfiguracaoInseguraError):
        _settings(shogun_auth_token="").validar_exposicao(bind)


# --- Servidor de verdade ----------------------------------------------------
#
# Os testes acima montam a pilha na mão. Estes sobem o uvicorn como processo,
# que é o único jeito de garantir que a leitura do frame continua funcionando
# com a versão instalada.


def _porta_livre() -> int:
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _uvicorn(host: str, env_extra: dict) -> "subprocess.Popen":
    import os
    import subprocess
    import sys
    from pathlib import Path

    env = {**os.environ, "SHOGUN_AUTH_TOKEN": "", **env_extra}
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", host, "--port", str(_porta_livre())],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def test_uvicorn_host_aberto_derruba_o_startup():
    """SHOGUN_HOST diz 127.0.0.1, a CLI diz 0.0.0.0 — vale a CLI."""
    processo = _uvicorn("0.0.0.0", {"SHOGUN_HOST": "127.0.0.1"})
    saida = processo.communicate(timeout=45)[0]

    assert processo.returncode != 0, saida
    assert "ConfiguracaoInseguraError" in saida
    assert "Application startup failed" in saida


def test_uvicorn_host_local_sobe_sem_token():
    """E o inverso não pode virar falso positivo: local sobe sem token."""
    processo = _uvicorn("127.0.0.1", {"SHOGUN_HOST": "0.0.0.0"})
    try:
        for _ in range(400):
            linha = processo.stdout.readline()
            if not linha and processo.poll() is not None:
                break
            if "Application startup complete" in linha:
                return
        raise AssertionError("servidor nao completou o startup")
    finally:
        processo.terminate()
        processo.wait(timeout=20)
