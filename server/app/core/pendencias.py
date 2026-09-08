"""Injeção de dependência do provedor de pendências.

O contrato vive em ``app.domain`` (módulo do agente-contratos); aqui fica apenas
a ligação com o FastAPI: qual implementação a aplicação usa por padrão e o ponto
de override em testes.
"""

from fastapi import Depends
from sqlalchemy.orm import Session as DbSession

from app.db import RepositorioPendencias, get_db
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


def get_pendencias_provider(
    db: DbSession = Depends(get_db),
) -> PendenciasProvider:
    """Dependência do FastAPI — sobrescrita via ``app.dependency_overrides``.

    Default: o orquestrador do próprio Shogun apoiado no banco, um provider por
    request sobre a sessão do request — o mesmo padrão de
    ``core/persistencia.py``. O banco é exigido aqui como no resto do servidor
    (sessões e mensagens já não funcionam sem ele); o modo em memória do
    ``ShogunOrquestradorProvider`` continua existindo, mas como construção
    explícita — útil em teste e em uso fora do servidor —, não como fallback
    silencioso. Trocar por ``MaestriProvider(...)`` quando a API existir.
    """
    return ShogunOrquestradorProvider(repositorio=RepositorioPendencias(db))
