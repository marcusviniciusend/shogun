"""Testes do historico de sessoes — SQLite em memoria, sem rede."""

from datetime import datetime


def _sessao_com_mensagens(repo, session_id: str, falas: list[tuple[str, str]]):
    """Cria a sessao e grava as falas em ordem. `falas` = [(autor, texto)]."""
    sessao = repo.criar_sessao(session_id)
    for autor, texto in falas:
        if autor == "usuario":
            repo.registrar_usuario(session_id, texto)
        else:
            repo.registrar_assistente(session_id, texto)
    return sessao


def _fixar_atividade(db, sessao, momento: datetime) -> None:
    """updated_at deterministico — a ordenacao do teste nao depende do relogio."""
    sessao.updated_at = momento
    db.add(sessao)
    db.commit()


def test_sessoes_sem_credenciais_retorna_401(client):
    assert client.get("/sessoes").status_code == 401


def test_mensagens_sem_credenciais_retorna_401(client):
    assert client.get("/sessoes/s1/mensagens").status_code == 401


def test_sem_sessoes_devolve_lista_vazia(client, auth):
    assert client.get("/sessoes", headers=auth).json() == {
        "total": 0,
        "sessoes": [],
    }


def test_lista_sessoes_ordenada_pela_atividade_mais_recente(client, auth, repo, db):
    antiga = _sessao_com_mensagens(repo, "antiga", [("usuario", "bom dia")])
    recente = _sessao_com_mensagens(repo, "recente", [("usuario", "boa noite")])
    _fixar_atividade(db, antiga, datetime(2026, 9, 1, 8, 0))
    _fixar_atividade(db, recente, datetime(2026, 9, 7, 22, 0))

    dados = client.get("/sessoes", headers=auth).json()

    assert dados["total"] == 2
    assert [s["id"] for s in dados["sessoes"]] == ["recente", "antiga"]
    assert dados["sessoes"][0]["atualizada_em"].startswith("2026-09-07")
    assert "criada_em" in dados["sessoes"][0]


def test_titulo_corta_na_sexta_palavra_com_reticencia(client, auth, repo):
    _sessao_com_mensagens(
        repo,
        "s1",
        [
            ("usuario", "me lembra de pagar a conta de luz amanha cedo"),
            ("shogun", "Anotado, Marcus."),
        ],
    )

    sessao = client.get("/sessoes", headers=auth).json()["sessoes"][0]

    assert sessao["titulo"] == "me lembra de pagar a conta…"
    assert sessao["total_mensagens"] == 2


def test_titulo_curto_sai_inteiro_sem_reticencia(client, auth, repo):
    _sessao_com_mensagens(repo, "s1", [("usuario", "bom dia")])

    sessao = client.get("/sessoes", headers=auth).json()["sessoes"][0]

    assert sessao["titulo"] == "bom dia"


def test_titulo_vem_da_primeira_fala_do_usuario_nao_do_shogun(client, auth, repo):
    _sessao_com_mensagens(
        repo,
        "s1",
        [("shogun", "Em que posso ajudar?"), ("usuario", "abre o spotify")],
    )

    sessao = client.get("/sessoes", headers=auth).json()["sessoes"][0]

    assert sessao["titulo"] == "abre o spotify"


def test_sessao_sem_fala_do_usuario_ganha_titulo_exibivel(client, auth, repo):
    repo.criar_sessao("vazia")

    sessao = client.get("/sessoes", headers=auth).json()["sessoes"][0]

    assert sessao["titulo"] == "(conversa vazia)"
    assert sessao["total_mensagens"] == 0


def test_mensagens_em_ordem_cronologica_com_autor_mapeado(client, auth, repo):
    _sessao_com_mensagens(
        repo,
        "s1",
        [
            ("usuario", "quais sao minhas pendencias?"),
            ("shogun", "Voce tem 2 pendencias."),
            ("usuario", "obrigado"),
        ],
    )

    dados = client.get("/sessoes/s1/mensagens", headers=auth).json()

    assert dados["session_id"] == "s1"
    assert [(m["autor"], m["texto"]) for m in dados["mensagens"]] == [
        ("usuario", "quais sao minhas pendencias?"),
        ("shogun", "Voce tem 2 pendencias."),
        ("usuario", "obrigado"),
    ]
    assert all("criada_em" in m for m in dados["mensagens"])


def test_sessao_inexistente_retorna_404(client, auth):
    resposta = client.get("/sessoes/nao-existe/mensagens", headers=auth)

    assert resposta.status_code == 404
    assert "nao-existe" in resposta.json()["detail"]


def test_conversa_pelo_comando_aparece_no_historico(client, auth, llm):
    """Ponta a ponta: o que o /comando grava e o que o historico lista."""
    corpo = {"session_id": None, "text": "bom dia, Shogun", "client": "desktop"}
    session_id = client.post("/comando", json=corpo, headers=auth).json()[
        "session_id"
    ]

    sessoes = client.get("/sessoes", headers=auth).json()
    mensagens = client.get(f"/sessoes/{session_id}/mensagens", headers=auth).json()

    assert sessoes["total"] == 1
    assert sessoes["sessoes"][0]["id"] == session_id
    assert sessoes["sessoes"][0]["titulo"] == "bom dia, Shogun"
    assert sessoes["sessoes"][0]["total_mensagens"] == 2
    assert [m["autor"] for m in mensagens["mensagens"]] == ["usuario", "shogun"]
