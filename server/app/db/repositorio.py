"""Repositório das conversas — a rota pede dados, não monta query."""

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.db.models import ROLE_ASSISTENTE, ROLE_USUARIO, Message, Session, agora_utc


def novo_id_de_sessao() -> str:
    """Id de sessão gerado pelo servidor.

    UUID4 em hex. O `CommandRequest` aceita um id vindo do cliente, mas quando
    ele vem nulo é aqui que o id nasce — ver a decisão registrada em
    `docs/DATABASE.md`.
    """
    return uuid.uuid4().hex


class RepositorioConversas:
    """Leitura e escrita de `sessions` e `messages`.

    Recebe a sessão do SQLAlchemy pronta (uma por request) em vez de abrir a
    sua: quem controla a transação é o request, não o repositório.
    """

    def __init__(self, db: DbSession) -> None:
        self._db = db

    # -- sessões -----------------------------------------------------------

    def obter_sessao(self, session_id: str) -> Session | None:
        return self._db.get(Session, session_id)

    def criar_sessao(self, session_id: str | None = None) -> Session:
        sessao = Session(id=session_id or novo_id_de_sessao())
        self._db.add(sessao)
        self._db.commit()
        return sessao

    def obter_ou_criar_sessao(self, session_id: str | None) -> Session:
        """A sessão da conversa, criando a linha se ainda não existir.

        Cobre os três casos do passo 2 do `DESIGN.md`: id nulo (servidor gera),
        id novo vindo do cliente (materializa a linha) e id conhecido.
        """
        if session_id is None:
            return self.criar_sessao()
        return self.obter_sessao(session_id) or self.criar_sessao(session_id)

    def marcar_atividade(self, sessao: Session) -> None:
        """Empurra `updated_at` — a sessão teve movimento agora."""
        sessao.updated_at = agora_utc()
        self._db.add(sessao)
        self._db.commit()

    # -- mensagens ---------------------------------------------------------

    def historico(self, session_id: str, limite: int | None = None) -> list[Message]:
        """As mensagens da sessão, em ordem canônica (por `id`).

        Com `limite`, devolve as **últimas** N — mas ainda em ordem crescente,
        que é como o prompt precisa lê-las.
        """
        consulta = select(Message).where(Message.session_id == session_id)

        if limite is None:
            return list(self._db.scalars(consulta.order_by(Message.id)))

        # Pega as N mais recentes pelo fim e reordena: evita carregar uma
        # conversa longa inteira só para descartar o começo.
        recentes = list(
            self._db.scalars(consulta.order_by(Message.id.desc()).limit(limite))
        )
        return list(reversed(recentes))

    def registrar_mensagem(self, session_id: str, role: str, content: str) -> Message:
        mensagem = Message(session_id=session_id, role=role, content=content)
        self._db.add(mensagem)
        self._db.commit()
        return mensagem

    def registrar_usuario(self, session_id: str, content: str) -> Message:
        return self.registrar_mensagem(session_id, ROLE_USUARIO, content)

    def registrar_assistente(self, session_id: str, content: str) -> Message:
        return self.registrar_mensagem(session_id, ROLE_ASSISTENTE, content)


def historico_como_texto(mensagens: Sequence[Message]) -> list[tuple[str, str]]:
    """`(role, content)` de cada mensagem — o que o montador de prompt consome."""
    return [(m.role, m.content) for m in mensagens]
