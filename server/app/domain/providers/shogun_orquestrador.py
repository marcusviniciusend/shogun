"""Provider de pendências do orquestrador próprio do Shogun.

Implementação local: as pendências vivem em um repositório do próprio Shogun.
Com `repositorio` injetado, o estado é persistente (hoje SQLite, via
`app.db.RepositorioPendencias`); sem ele, fica em memória nesta instância —
default que os testes e o modo sem banco continuam usando.

O domínio segue puro: este módulo não conhece SQLAlchemy nem FastAPI. O que ele
exige do repositório está descrito no protocolo `RepositorioPendencias` abaixo,
e o acesso concreto ao banco vive em `app/db/repositorio.py`.
"""

from datetime import datetime, timezone
from typing import Protocol

from ..pendencias import Pendencia, PendenciasProvider, StatusAgente


class RepositorioPendencias(Protocol):
    """O que o provider precisa de um repositório persistente.

    Protocolo estrutural: `app.db.RepositorioPendencias` o satisfaz sem
    importar nada daqui. Timestamps devolvidos são aware em UTC; um timestamp
    naive registrado é interpretado como UTC.
    """

    def listar(self) -> list[Pendencia]:
        """Todas as pendências, mais urgentes primeiro (prioridade desc,
        timestamp asc)."""
        ...

    def status_do_agente(self, agente_id: str) -> StatusAgente | None:
        """Status corrente, ou `None` para agente desconhecido."""
        ...

    def registrar(self, pendencia: Pendencia) -> None:
        """Grava a pendência e atualiza o status/nome do agente."""
        ...

    def atualizar_status(self, agente_id: str, status: StatusAgente) -> None:
        """Atualiza só o status; não exige pendência registrada."""
        ...

    def limpar(self, agente_id: str) -> None:
        """Apaga as pendências do agente, preservando o status dele."""
        ...


class ShogunOrquestradorProvider(PendenciasProvider):
    """Pendências mantidas pelo orquestrador do próprio Shogun.

    Com `repositorio`, toda leitura e escrita passa por ele; sem, o estado fica
    em memória nesta instância. As duas formas têm a mesma semântica — os
    testes de domínio rodam contra ambas.
    """

    def __init__(self, repositorio: RepositorioPendencias | None = None) -> None:
        self._repositorio = repositorio
        self._pendencias: dict[str, list[Pendencia]] = {}
        self._status: dict[str, StatusAgente] = {}

    def get_pendencias_agentes(self) -> list[Pendencia]:
        if self._repositorio is not None:
            return self._repositorio.listar()
        pendencias = [p for lista in self._pendencias.values() for p in lista]
        return sorted(pendencias, key=lambda p: (-p.prioridade, p.timestamp))

    def get_status_agente(self, agente_id: str) -> StatusAgente:
        if self._repositorio is not None:
            status = self._repositorio.status_do_agente(agente_id)
            # Mesmo default do modo em memória: quem nunca apareceu não deve
            # nada.
            return status if status is not None else StatusAgente.CONCLUIDO
        return self._status.get(agente_id, StatusAgente.CONCLUIDO)

    # -- escrita -----------------------------------------------------------
    # Usado pelo orquestrador ao acompanhar seus agentes. Não faz parte do
    # contrato `PendenciasProvider`, que é somente de leitura.

    def registrar_pendencia(
        self,
        agente_id: str,
        agente_nome: str,
        descricao: str,
        status: StatusAgente = StatusAgente.PENDENTE,
        prioridade: int = 0,
        timestamp: datetime | None = None,
    ) -> Pendencia:
        pendencia = Pendencia(
            agente_id=agente_id,
            agente_nome=agente_nome,
            status=status,
            descricao=descricao,
            timestamp=timestamp or datetime.now(timezone.utc),
            prioridade=prioridade,
        )
        if self._repositorio is not None:
            self._repositorio.registrar(pendencia)
        else:
            self._pendencias.setdefault(agente_id, []).append(pendencia)
            self._status[agente_id] = status
        return pendencia

    def atualizar_status(self, agente_id: str, status: StatusAgente) -> None:
        if self._repositorio is not None:
            self._repositorio.atualizar_status(agente_id, status)
        else:
            self._status[agente_id] = status

    def limpar_pendencias(self, agente_id: str) -> None:
        if self._repositorio is not None:
            self._repositorio.limpar(agente_id)
        else:
            self._pendencias.pop(agente_id, None)
