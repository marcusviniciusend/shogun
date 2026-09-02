"""Autenticação dos clientes por token fixo (Bearer)."""

import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings, settings

# auto_error=False para podermos devolver uma mensagem própria quando falta o header.
_bearer = HTTPBearer(auto_error=False)


def get_settings() -> Settings:
    """Dependência que expõe a configuração — facilita override em testes."""
    return settings


async def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    config: Settings = Depends(get_settings),
) -> None:
    """Valida o Bearer token fixo definido em ``SHOGUN_AUTH_TOKEN``.

    Se o token não estiver configurado, a autenticação fica desligada — útil no
    desenvolvimento local, mas o servidor avisa no log de inicialização.
    """
    if not config.shogun_auth_token:
        return

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais ausentes.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Comparação em tempo constante para não vazar o token por timing.
    if not secrets.compare_digest(credentials.credentials, config.shogun_auth_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido.",
            headers={"WWW-Authenticate": "Bearer"},
        )
