"""Persistência do Shogun: modelos e repositório.

A camada HTTP nunca monta query — pede "o histórico desta sessão" ao
repositório. É a mesma estratégia de `LLMProvider` e `PendenciasProvider`: a
decisão concreta (hoje SQLite) fica atrás de uma interface, e trocá-la não
reescreve quem a usa. Ver `docs/DATABASE.md`.
"""

from app.db.models import Base, Message, Session
from app.db.repositorio import RepositorioConversas

__all__ = [
    "Base",
    "Message",
    "RepositorioConversas",
    "Session",
]
