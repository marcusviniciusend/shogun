"""Testes da rota POST /comando — os 8 casos validados no smoke test."""

from app.core.llm import ComandoInterpretado
from app.core.pendencias import PendenciasProviderStub, get_pendencias_provider


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_sem_credenciais_retorna_401(client, corpo):
    assert client.post("/comando", json=corpo).status_code == 401


def test_token_invalido_retorna_401(client, corpo):
    resposta = client.post(
        "/comando", json=corpo, headers={"Authorization": "Bearer errado"}
    )
    assert resposta.status_code == 401


def test_acao_conversar_usa_resposta_livre(client, corpo, auth, llm):
    resposta = client.post("/comando", json=corpo, headers=auth)

    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["session_id"] == "s1"
    assert dados["text"] == "Olá, Marcus."
    assert dados["actions"] == []
    assert llm.chamadas == ["bom dia"]


def test_acao_consultar_pendencias_lista_itens(client, corpo, auth, llm):
    llm.resposta = ComandoInterpretado(
        acao="consultar_pendencias", parametros={}, resposta_falada="ok"
    )

    dados = client.post("/comando", json=corpo, headers=auth).json()

    assert "Assinar contrato (até sexta)" in dados["text"]
    assert "Ligar pro contador" in dados["text"]
    assert dados["actions"] == [
        {"agent": "pendencias", "status": "ok", "detail": "2 pendências"}
    ]


def test_acao_abrir_app_e_placeholder(client, corpo, auth, llm):
    llm.resposta = ComandoInterpretado(
        acao="abrir_app", parametros={"app": "Spotify"}, resposta_falada="ok"
    )

    dados = client.post("/comando", json=corpo, headers=auth).json()

    assert "Spotify" in dados["text"]
    assert dados["actions"][0]["status"] == "error"
    assert "não implementado" in dados["actions"][0]["detail"]


def test_comando_vazio_retorna_422(client, corpo, auth):
    resposta = client.post("/comando", json={**corpo, "text": "   "}, headers=auth)
    assert resposta.status_code == 422


def test_provedor_de_pendencias_ausente_nao_afirma_que_esta_em_dia(
    client, corpo, auth, llm
):
    """O stub não pode virar 'você não tem pendências' — seria mentir pro Marcus."""
    from app.main import app

    app.dependency_overrides[get_pendencias_provider] = PendenciasProviderStub
    llm.resposta = ComandoInterpretado(
        acao="consultar_pendencias", parametros={}, resposta_falada="ok"
    )

    dados = client.post("/comando", json=corpo, headers=auth).json()

    assert "ainda não está conectada" in dados["text"]
    assert dados["actions"][0]["status"] == "error"


def test_llm_indisponivel_retorna_503(client, corpo, auth, llm):
    llm.erro = "sem chave"
    resposta = client.post("/comando", json=corpo, headers=auth)
    assert resposta.status_code == 503
