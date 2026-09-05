"""Injeção de dependência do repositório de conversas.

Mesmo papel de `core/pendencias.py`: o contrato e a implementação vivem em
`app.db`; aqui fica só a ligação com o FastAPI e o ponto de override em testes.
"""

from fastapi import Depends
from sqlalchemy.orm import Session as DbSession

from app.db import RepositorioConversas, get_db

__all__ = ["RepositorioConversas", "get_repositorio"]


def get_repositorio(db: DbSession = Depends(get_db)) -> RepositorioConversas:
    """Um repositório por request, sobre a sessão de banco do request."""
    return RepositorioConversas(db)
