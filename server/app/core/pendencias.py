"""Injeção de dependência do provedor de pendências.

O contrato vive em ``app.domain`` (módulo do agente-contratos); aqui fica apenas
a ligação com o FastAPI: qual implementação a aplicação usa por padrão e o ponto
de override em testes.
"""

from app.domain import (
    Pendencia,
    PendenciasProvider,
    ShogunOrquestradorProvider,
    StatusAgente,
)

__all__ = [
    "Pendencia",
    "PendenciasProvider",
    "StatusAgente",
    "get_pendencias_provider",
]

# Default: o orquestrador do próprio Shogun, hoje em memória. É uma
# implementação real do contrato — quando não há nada registrado, a lista é
# legitimamente vazia. Trocar por ``MaestriProvider(...)`` quando a API existir.
_provider: PendenciasProvider = ShogunOrquestradorProvider()


def get_pendencias_provider() -> PendenciasProvider:
    """Dependência do FastAPI — sobrescrita via ``app.dependency_overrides``."""
    return _provider
