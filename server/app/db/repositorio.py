"""Repositórios do banco — quem consome pede dados, não monta query."""

import uuid
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import NamedTuple

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session as DbSession

from app.db.models import (
    ROLE_ASSISTENTE,
    ROLE_USUARIO,
    Agente,
    Message,
    MessageUso,
    PendenciaAgente,
    Session,
    agora_utc,
)
from app.domain import Pendencia, StatusAgente


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

    # -- uso de tokens -----------------------------------------------------

    def registrar_uso(
        self,
        message_id: int,
        provider: str,
        input_tokens: int,
        output_tokens: int,
    ) -> MessageUso:
        uso = MessageUso(
            message_id=message_id,
            provider=provider,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        self._db.add(uso)
        self._db.commit()
        return uso

    def consumo_por_provider(
        self,
        inicio: datetime | None = None,
        fim: datetime | None = None,
    ) -> list["ConsumoProvider"]:
        """Tokens somados por provedor no período. Datas em UTC naive.

        `inicio` inclusivo e `fim` exclusivo — o par (dia, dia+1) cobre um dia
        inteiro sem depender de microssegundo final. `None` = sem corte.
        """
        consulta = select(
            MessageUso.provider,
            func.count(MessageUso.id),
            func.coalesce(func.sum(MessageUso.input_tokens), 0),
            func.coalesce(func.sum(MessageUso.output_tokens), 0),
        ).group_by(MessageUso.provider)

        if inicio is not None:
            consulta = consulta.where(MessageUso.created_at >= inicio)
        if fim is not None:
            consulta = consulta.where(MessageUso.created_at < fim)

        return [
            ConsumoProvider(provider, int(mensagens), int(entrada), int(saida))
            for provider, mensagens, entrada, saida in self._db.execute(consulta)
        ]


class ConsumoProvider(NamedTuple):
    """Agregado de consumo de um provedor num período."""

    provider: str
    mensagens: int
    input_tokens: int
    output_tokens: int


def historico_como_texto(mensagens: Sequence[Message]) -> list[tuple[str, str]]:
    """`(role, content)` de cada mensagem — o que o montador de prompt consome."""
    return [(m.role, m.content) for m in mensagens]


def _utc_naive(momento: datetime) -> datetime:
    """Normaliza para o formato interno do banco (UTC sem tzinfo).

    Valor aware é convertido; valor naive é assumido como UTC — a mesma
    convenção de `agora_utc()` (ver `docs/DATABASE.md`).
    """
    if momento.tzinfo is not None:
        return momento.astimezone(timezone.utc).replace(tzinfo=None)
    return momento


class RepositorioPendencias:
    """Leitura e escrita de `agentes` e `pendencias`.

    Implementa o protocolo que o `ShogunOrquestradorProvider` espera receber
    injetado. Fala o vocabulário do domínio (`Pendencia`, `StatusAgente`) na
    borda: quem consome nunca vê linha de tabela. Timestamps entram em qualquer
    fuso (naive = UTC) e saem sempre aware em UTC.
    """

    def __init__(self, db: DbSession) -> None:
        self._db = db

    # -- leitura (contrato PendenciasProvider) -------------------------------

    def listar(self) -> list[Pendencia]:
        """Todas as pendências, mais urgentes primeiro — a mesma ordenação do
        provider em memória, com `id` de desempate para ser determinística."""
        consulta = (
            select(PendenciaAgente, Agente.nome)
            .join(Agente, PendenciaAgente.agente_id == Agente.id)
            .order_by(
                PendenciaAgente.prioridade.desc(),
                PendenciaAgente.created_at,
                PendenciaAgente.id,
            )
        )
        return [
            self._como_dominio(linha, nome)
            for linha, nome in self._db.execute(consulta)
        ]

    def status_do_agente(self, agente_id: str) -> StatusAgente | None:
        """`None` para agente desconhecido — o default é decisão do provider."""
        agente = self._db.get(Agente, agente_id)
        return StatusAgente(agente.status) if agente is not None else None

    # -- escrita (usada pelo orquestrador) -----------------------------------

    def registrar(self, pendencia: Pendencia) -> None:
        self._garantir_agente(
            pendencia.agente_id, nome=pendencia.agente_nome, status=pendencia.status
        )
        self._db.add(
            PendenciaAgente(
                agente_id=pendencia.agente_id,
                descricao=pendencia.descricao,
                status=pendencia.status.value,
                prioridade=pendencia.prioridade,
                created_at=_utc_naive(pendencia.timestamp),
            )
        )
        self._db.commit()

    def atualizar_status(self, agente_id: str, status: StatusAgente) -> None:
        self._garantir_agente(agente_id, nome=None, status=status)
        self._db.commit()

    def limpar(self, agente_id: str) -> None:
        """Apaga as pendências do agente; o status dele fica (é conhecimento
        sobre o agente, não sobre a fila)."""
        self._db.execute(
            delete(PendenciaAgente).where(PendenciaAgente.agente_id == agente_id)
        )
        self._db.commit()

    # -- internos -------------------------------------------------------------

    def _garantir_agente(
        self, agente_id: str, nome: str | None, status: StatusAgente
    ) -> Agente:
        agente = self._db.get(Agente, agente_id)
        if agente is None:
            agente = Agente(id=agente_id, nome=nome, status=status.value)
            self._db.add(agente)
        else:
            agente.status = status.value
            if nome is not None:
                agente.nome = nome
        return agente

    @staticmethod
    def _como_dominio(linha: PendenciaAgente, nome: str | None) -> Pendencia:
        return Pendencia(
            agente_id=linha.agente_id,
            # `nome` nulo só acontece para agente que nunca registrou pendência,
            # e esse não aparece neste join — o fallback é cinto de segurança.
            agente_nome=nome or linha.agente_id,
            status=StatusAgente(linha.status),
            descricao=linha.descricao,
            timestamp=linha.created_at.replace(tzinfo=timezone.utc),
            prioridade=linha.prioridade,
        )
