"""Rotas HTTP e WebSocket do servidor Shogun."""

from app.api.comando import router as comando_router

__all__ = ["comando_router"]
