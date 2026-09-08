"""Testes do rate limit — janela com relogio fake e rotas com limites baixos."""

import pytest

from app.core.rate_limit import JanelaDeslizante
from app.core.security import get_settings


# --- janela deslizante (unidade, relogio controlado) ----------------------


def _janela_com_relogio():
    tempo = {"agora": 0.0}
    janela = JanelaDeslizante(relogio=lambda: tempo["agora"])
    return janela, tempo


def test_janela_permite_ate_o_limite_e_bloqueia_o_excedente():
    janela, _ = _janela_com_relogio()

    assert janela.registrar("token", 2) is None
    assert janela.registrar("token", 2) is None
    assert janela.registrar("token", 2) == 60.0


def test_janela_informa_quanto_falta_para_liberar():
    janela, tempo = _janela_com_relogio()
    janela.registrar("token", 1)
    tempo["agora"] = 15.0

    assert janela.registrar("token", 1) == 45.0


def test_janela_desliza_e_libera_depois_de_60s():
    janela, tempo = _janela_com_relogio()
    janela.registrar("token", 1)

    tempo["agora"] = 59.9
    assert janela.registrar("token", 1) is not None
    tempo["agora"] = 60.0
    assert janela.registrar("token", 1) is None


def test_janela_separa_as_chaves():
    janela, _ = _janela_com_relogio()
    janela.registrar("token-a", 1)

    assert janela.registrar("token-b", 1) is None


# --- rotas (limites baixos via override de settings) -----------------------


@pytest.fixture
def limites_apertados(client, settings_teste):
    """Limites minimos para estourar sem loop grande: 2 comando, 2 leitura."""
    from app.main import app

    apertado = settings_teste.model_copy(
        update={
            "shogun_rate_limit_comando_por_minuto": 2,
            "shogun_rate_limit_leitura_por_minuto": 2,
        }
    )
    app.dependency_overrides[get_settings] = lambda: apertado
    return apertado


def test_comando_estoura_com_429_e_retry_after(client, corpo, auth, limites_apertados):
    assert client.post("/comando", json=corpo, headers=auth).status_code == 200
    assert client.post("/comando", json=corpo, headers=auth).status_code == 200

    resposta = client.post("/comando", json=corpo, headers=auth)

    assert resposta.status_code == 429
    segundos = int(resposta.headers["Retry-After"])
    assert 1 <= segundos <= 60
    assert "2 chamadas por minuto" in resposta.json()["detail"]
    assert "/comando" in resposta.json()["detail"]


def test_rotas_de_leitura_dividem_um_balde_frouxo(client, auth, limites_apertados):
    """O balde de leitura e um so: /pendencias e /sessoes somam nele."""
    assert client.get("/pendencias", headers=auth).status_code == 200
    assert client.get("/sessoes", headers=auth).status_code == 200

    resposta = client.get("/sessoes", headers=auth)

    assert resposta.status_code == 429
    assert "Retry-After" in resposta.headers


def test_estourar_o_comando_nao_bloqueia_a_leitura(client, corpo, auth, limites_apertados):
    """Baldes separados: o painel continua lendo mesmo com a voz limitada."""
    for _ in range(3):
        client.post("/comando", json=corpo, headers=auth)

    assert client.get("/pendencias", headers=auth).status_code == 200


def test_polling_do_painel_nao_esbarra_no_limite_default(client, auth):
    """Uso normal: polling de 30s = 2/min por endpoint, contra 120/min.

    Simula um minuto de painel aberto (2 ciclos x 3 endpoints) com folga 4x —
    nada pode responder 429 com os defaults.
    """
    for _ in range(8):
        assert client.get("/pendencias", headers=auth).status_code == 200
        assert client.get("/sessoes", headers=auth).status_code == 200
        assert client.get("/consumo", headers=auth).status_code == 200


def test_token_invalido_vira_401_sem_consumir_cota(client, corpo, auth, limites_apertados):
    """Autenticacao roda antes do rate limit: 401 nao gasta o balde de ninguem."""
    errado = {"Authorization": "Bearer errado"}
    for _ in range(3):
        assert client.post("/comando", json=corpo, headers=errado).status_code == 401

    assert client.post("/comando", json=corpo, headers=auth).status_code == 200


def test_limite_zero_desliga_o_balde(client, corpo, auth, settings_teste):
    from app.main import app

    desligado = settings_teste.model_copy(
        update={"shogun_rate_limit_comando_por_minuto": 0}
    )
    app.dependency_overrides[get_settings] = lambda: desligado

    for _ in range(25):
        assert client.post("/comando", json=corpo, headers=auth).status_code == 200
