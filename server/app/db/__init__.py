"""Persistência do Shogun: modelos, engine e repositório.

A camada HTTP nunca monta query — pede "o histórico desta sessão" ao
repositório. É a mesma estratégia de `LLMProvider` e `PendenciasProvider`: a
decisão concreta (hoje SQLite) fica atrás de uma interface, e trocá-la não
reescreve quem a usa. Ver `docs/DATABASE.md`.
"""

from app.db.engine import (
    criar_engine,
    criar_tabelas,
    engine,
    get_db,
    sessionmaker_do_engine,
)
from app.db.models import Agente, Base, Message, MessageUso, PendenciaAgente, Session
from app.db.repositorio import RepositorioConversas, RepositorioPendencias

__all__ = [
    "Agente",
    "Base",
    "Message",
    "MessageUso",
    "PendenciaAgente",
    "RepositorioConversas",
    "RepositorioPendencias",
    "Session",
    "criar_engine",
    "criar_tabelas",
    "engine",
    "get_db",
    "sessionmaker_do_engine",
]
