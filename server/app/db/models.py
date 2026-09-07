"""Modelos de `sessions` e `messages` — o schema de `docs/DATABASE.md`.

Só entra campo que algum passo do fluxo precisa. Tipos genéricos de
`sqlalchemy` (nada de `sqlite.*`), porque a portabilidade para Postgres é
consequência de escrever assim, não do ORM por si.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def agora_utc() -> datetime:
    """Timestamp em UTC, sempre — e sem `tzinfo`.

    Gravar em UTC desde o primeiro dia é o único item da lista de portabilidade
    de `docs/DATABASE.md` que, se ignorado, corrompe dado já gravado em vez de
    só dar trabalho depois.

    O `tzinfo` sai fora de propósito. O SQLite não tem tipo de data nativo: ele
    guarda texto e devolve `datetime` naive, sempre. Se gravássemos valores
    aware, todo valor lido do banco seria naive e todo valor novo seria aware —
    e comparar os dois levanta `TypeError`. Um único formato interno, UTC naive,
    elimina a classe inteira de bug.

    Na migração para Postgres isto vira `timestamptz`: ver o checklist em
    `docs/DATABASE.md`.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Session(Base):
    """Uma conversa."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=agora_utc)
    # Atualizado a cada resposta do assistente (passo 8 do DESIGN.md). É campo,
    # e não MAX(messages.created_at) derivado, para listar sessões por atividade
    # e expirar as antigas sem varrer messages.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=agora_utc, onupdate=agora_utc
    )

    messages: Mapped[list["Message"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        # A ordenação canônica é por id, e vale também aqui.
        order_by="Message.id",
    )


class Message(Base):
    """Uma fala, do Marcus ou do Shogun."""

    __tablename__ = "messages"

    # INTEGER PRIMARY KEY no SQLite, IDENTITY no Postgres: declarar genérico e
    # deixar o dialeto resolver.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=agora_utc)

    session: Mapped[Session] = relationship(back_populates="messages")

    __table_args__ = (
        # Exatamente a consulta do passo 3: as ultimas N mensagens de uma
        # sessao, em ordem.
        Index("ix_messages_session_id_id", "session_id", "id"),
    )


class MessageUso(Base):
    """Consumo de tokens da chamada de LLM que gerou uma fala do Shogun.

    Tabela separada, e não colunas em `messages`, porque o uso só existe para
    mensagens do assistente atendidas por um provedor que reporta medição — em
    `messages` os campos seriam nulos na metade das linhas. Aqui também mora o
    `provider`, cobrindo o campo "deliberadamente fora" do schema original
    (ver `docs/DATABASE.md`).
    """

    __tablename__ = "messages_uso"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # unique: uma chamada de LLM por fala do assistente — duas medições para a
    # mesma mensagem seria bug de gravação, não dado.
    message_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=agora_utc)

    __table_args__ = (
        # A consulta do GET /consumo: soma de tokens num período.
        Index("ix_messages_uso_created_at", "created_at"),
    )


class Agente(Base):
    """Um agente sob observação do orquestrador do Shogun.

    Linha própria, e não coluna derivada de `pendencias`, porque o status de um
    agente é independente das pendências dele: `atualizar_status` funciona sem
    pendência registrada, e limpar a fila não apaga o que se sabe do agente —
    semântica que o `ShogunOrquestradorProvider` já tinha em memória.
    """

    __tablename__ = "agentes"

    # Id vem do orquestrador (ex.: slug do agente), não é gerado aqui.
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    # Nulo quando o agente só teve status atualizado, sem pendência registrada
    # (o nome chega junto com a primeira pendência).
    nome: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Valores de `StatusAgente` (domínio). String, e não Enum do SQLAlchemy:
    # variante nova no domínio não pode exigir migração de schema.
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=agora_utc, onupdate=agora_utc
    )

    pendencias: Mapped[list["PendenciaAgente"]] = relationship(
        back_populates="agente", cascade="all, delete-orphan"
    )


class PendenciaAgente(Base):
    """Uma pendência reportada por um agente — espelho persistente de
    `app.domain.Pendencia` (`agente_nome` vive em `agentes.nome`)."""

    __tablename__ = "pendencias"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agente_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("agentes.id", ondelete="CASCADE"), nullable=False
    )
    descricao: Mapped[str] = mapped_column(Text, nullable=False)
    # Status da pendência no momento do registro; o status corrente do agente
    # fica em `agentes.status`.
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    prioridade: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # `Pendencia.timestamp` do domínio, em UTC naive como todo o banco.
    created_at: Mapped[datetime] = mapped_column(DateTime, default=agora_utc)

    agente: Mapped[Agente] = relationship(back_populates="pendencias")

    __table_args__ = (
        # As duas consultas do provider: limpar/agrupar por agente e a listagem
        # global ordenada por urgência.
        Index("ix_pendencias_agente_id", "agente_id"),
        Index("ix_pendencias_prioridade_created_at", "prioridade", "created_at"),
    )


ROLE_USUARIO = "user"
ROLE_ASSISTENTE = "assistant"
