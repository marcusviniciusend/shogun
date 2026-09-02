"""Provider de pendências do orquestrador próprio do Shogun.

Implementação local: as pendências vivem em um repositório (banco ou fila) do
próprio Shogun. A classe já traz a estrutura de acesso; hoje opera sobre um
armazenamento em memória, que serve de default e de fixture para testes.
"""

from datetime import datetime, timezone

from ..pendencias import Pendencia, PendenciasProvider, StatusAgente


class ShogunOrquestradorProvider(PendenciasProvider):
    """Pendências mantidas pelo orquestrador do próprio Shogun.

    `repositorio` é o ponto de extensão para o backend real (SQLite, Postgres ou
    uma fila). Enquanto ele não existe, o estado fica em memória nesta instância.
    """

    def __init__(self, repositorio: object | None = None) -> None:
        # TODO: trocar `object` pela interface do repositório quando ela existir.
        self._repositorio = repositorio
        self._pendencias: dict[str, list[Pendencia]] = {}
        self._status: dict[str, StatusAgente] = {}

    def get_pendencias_agentes(self) -> list[Pendencia]:
        pendencias = [p for lista in self._pendencias.values() for p in lista]
        return sorted(pendencias, key=lambda p: (-p.prioridade, p.timestamp))

    def get_status_agente(self, agente_id: str) -> StatusAgente:
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
        self._pendencias.setdefault(agente_id, []).append(pendencia)
        self._status[agente_id] = status
        return pendencia

    def atualizar_status(self, agente_id: str, status: StatusAgente) -> None:
        self._status[agente_id] = status

    def limpar_pendencias(self, agente_id: str) -> None:
        self._pendencias.pop(agente_id, None)
