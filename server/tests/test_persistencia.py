"""Persistência de sessões e mensagens.

Todo teste roda contra um SQLite em memória, criado pela fixture `db_engine`.
O banco real nunca é aberto: `get_db` é sobrescrito no `client`.
"""

from datetime import datetime

from sqlalchemy import select

from app.core.llm import ComandoInterpretado
from app.core.llm.historico import montar_prompt
from app.db import Message, Session
from app.db.repositorio import novo_id_de_sessao

# --- Sessões ----------------------------------------------------------------


def test_sessao_criada_sem_id_recebe_um_gerado(repo):
    sessao = repo.criar_sessao()

    assert sessao.id
    assert repo.obter_sessao(sessao.id) is not None


def test_ids_gerados_nao_se_repetem():
    assert len({novo_id_de_sessao() for _ in range(500)}) == 500


def test_id_vindo_do_cliente_e_respeitado(repo):
    sessao = repo.obter_ou_criar_sessao("sessao-do-cliente")

    assert sessao.id == "sessao-do-cliente"


def test_sessao_existente_nao_e_recriada(repo):
    primeira = repo.criar_sessao("s1")
    repo.registrar_usuario("s1", "oi")

    segunda = repo.obter_ou_criar_sessao("s1")

    assert segunda.id == primeira.id
    assert len(repo.historico("s1")) == 1


def test_marcar_atividade_empurra_updated_at(repo, db):
    sessao = repo.criar_sessao("s1")
    antigo = datetime(2020, 1, 1)  # naive, como tudo que vai para o banco
    sessao.updated_at = antigo
    db.commit()

    repo.marcar_atividade(sessao)

    assert repo.obter_sessao("s1").updated_at > antigo


# --- Mensagens --------------------------------------------------------------


def test_mensagens_sao_persistidas_com_papel_e_texto(repo, db):
    repo.criar_sessao("s1")
    repo.registrar_usuario("s1", "quais sao minhas pendencias?")
    repo.registrar_assistente("s1", "Voce tem 2 pendencias.")

    gravadas = list(db.scalars(select(Message).order_by(Message.id)))

    assert [(m.role, m.content) for m in gravadas] == [
        ("user", "quais sao minhas pendencias?"),
        ("assistant", "Voce tem 2 pendencias."),
    ]


def test_historico_vem_ordenado_por_id_e_nao_por_timestamp(repo, db):
    """Mensagens no mesmo instante não teriam desempate por `created_at`."""
    repo.criar_sessao("s1")
    for texto in ("primeira", "segunda", "terceira", "quarta"):
        repo.registrar_usuario("s1", texto)

    # Empata todos os timestamps: só a ordem de inserção pode desempatar.
    mesmo_instante = datetime(2026, 9, 5, 12, 0)
    for mensagem in db.scalars(select(Message)):
        mensagem.created_at = mesmo_instante
    db.commit()

    assert [m.content for m in repo.historico("s1")] == [
        "primeira",
        "segunda",
        "terceira",
        "quarta",
    ]


def test_historico_com_limite_traz_as_ultimas_em_ordem_crescente(repo):
    repo.criar_sessao("s1")
    for i in range(10):
        repo.registrar_usuario("s1", f"msg {i}")

    recentes = repo.historico("s1", limite=3)

    assert [m.content for m in recentes] == ["msg 7", "msg 8", "msg 9"]


def test_historico_e_por_sessao(repo):
    repo.criar_sessao("s1")
    repo.criar_sessao("s2")
    repo.registrar_usuario("s1", "da s1")
    repo.registrar_usuario("s2", "da s2")

    assert [m.content for m in repo.historico("s1")] == ["da s1"]


def test_sessao_nova_tem_historico_vazio(repo):
    repo.criar_sessao("s1")

    assert repo.historico("s1") == []


# --- Montagem do prompt -----------------------------------------------------


def test_sem_historico_o_prompt_e_o_proprio_comando():
    assert montar_prompt([], "bom dia") == "bom dia"


def test_historico_entra_como_bloco_antes_do_comando():
    prompt = montar_prompt(
        [("user", "quais sao minhas pendencias?"), ("assistant", "Voce tem 2.")],
        "e as outras?",
    )

    assert "Histórico da conversa" in prompt
    assert "Marcus: quais sao minhas pendencias?" in prompt
    assert "Shogun: Voce tem 2." in prompt
    # O comando novo fica por último — é o que o modelo tem que responder.
    assert prompt.rstrip().endswith("e as outras?")
    assert prompt.index("quais sao minhas") < prompt.index("e as outras?")


# --- Fluxo completo do /comando ---------------------------------------------


def _corpo(texto="bom dia", session_id=...):
    corpo = {"text": texto, "client": "desktop"}
    if session_id is not ...:
        corpo["session_id"] = session_id
    return corpo


def test_comando_sem_session_id_cria_sessao_e_devolve_o_id(client, auth, db):
    dados = client.post("/comando", json=_corpo(), headers=auth).json()

    assert dados["session_id"]
    assert db.get(Session, dados["session_id"]) is not None


def test_session_id_nulo_tambem_cria_sessao(client, auth):
    dados = client.post("/comando", json=_corpo(session_id=None), headers=auth).json()

    assert dados["session_id"]


def test_comando_grava_a_pergunta_e_a_resposta(client, auth, db, llm):
    llm.resposta = ComandoInterpretado(
        acao="conversar", parametros={}, resposta_falada="Bom dia, Marcus."
    )

    dados = client.post("/comando", json=_corpo("bom dia"), headers=auth).json()

    gravadas = list(
        db.scalars(
            select(Message)
            .where(Message.session_id == dados["session_id"])
            .order_by(Message.id)
        )
    )
    assert [(m.role, m.content) for m in gravadas] == [
        ("user", "bom dia"),
        ("assistant", "Bom dia, Marcus."),
    ]


def test_sessao_existente_e_reaproveitada(client, auth, db):
    primeiro = client.post("/comando", json=_corpo("bom dia"), headers=auth).json()
    sid = primeiro["session_id"]

    segundo = client.post(
        "/comando", json=_corpo("e agora?", session_id=sid), headers=auth
    ).json()

    assert segundo["session_id"] == sid
    assert db.scalar(select(Session).where(Session.id == sid)) is not None
    assert len(list(db.scalars(select(Message).where(Message.session_id == sid)))) == 4


def test_historico_da_sessao_chega_ao_llm(client, auth, llm):
    """A segunda pergunta tem que ir ao modelo com a primeira como contexto."""
    llm.resposta = ComandoInterpretado(
        acao="conversar", parametros={}, resposta_falada="Voce tem 2 pendencias."
    )
    sid = client.post(
        "/comando", json=_corpo("quais sao minhas pendencias?"), headers=auth
    ).json()["session_id"]

    client.post("/comando", json=_corpo("e as outras?", session_id=sid), headers=auth)

    primeiro, segundo = llm.chamadas
    # A primeira chamada não tem contexto nenhum: a conversa acabou de começar.
    assert primeiro == "quais sao minhas pendencias?"
    assert "Marcus: quais sao minhas pendencias?" in segundo
    assert "Shogun: Voce tem 2 pendencias." in segundo
    assert segundo.rstrip().endswith("e as outras?")


def test_comando_novo_nao_aparece_duplicado_no_proprio_prompt(client, auth, llm):
    """O histórico é lido antes do INSERT — senão o texto atual viria duas vezes."""
    client.post("/comando", json=_corpo("bom dia"), headers=auth)

    assert llm.chamadas == ["bom dia"]


def test_falha_do_llm_nao_apaga_a_pergunta_do_historico(client, auth, db, llm):
    """503 no modelo não pode sumir com o que o Marcus falou."""
    llm.erro = "sem chave"

    resposta = client.post("/comando", json=_corpo("bom dia"), headers=auth)

    assert resposta.status_code == 503
    gravadas = list(db.scalars(select(Message).order_by(Message.id)))
    assert [(m.role, m.content) for m in gravadas] == [("user", "bom dia")]


def test_comando_vazio_nao_cria_sessao(client, auth, db):
    resposta = client.post("/comando", json=_corpo("   "), headers=auth)

    assert resposta.status_code == 422
    assert db.scalars(select(Session)).all() == []


def test_updated_at_avanca_a_cada_comando(client, auth, db):
    sid = client.post("/comando", json=_corpo("bom dia"), headers=auth).json()[
        "session_id"
    ]
    db.expire_all()
    primeiro = db.get(Session, sid).updated_at

    client.post("/comando", json=_corpo("e agora?", session_id=sid), headers=auth)
    db.expire_all()

    assert db.get(Session, sid).updated_at >= primeiro


def test_sessao_desconhecida_vinda_do_cliente_e_materializada(client, auth, db):
    """O cliente pode trazer um id que o servidor nunca viu."""
    dados = client.post(
        "/comando", json=_corpo("bom dia", session_id="id-do-cliente"), headers=auth
    ).json()

    assert dados["session_id"] == "id-do-cliente"
    assert db.get(Session, "id-do-cliente") is not None
