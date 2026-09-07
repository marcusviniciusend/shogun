"""Rotas HTTP e WebSocket do servidor Shogun."""

from app.api.comando import router as comando_router
from app.api.consumo import router as consumo_router
from app.api.pendencias import router as pendencias_router

__all__ = ["comando_router", "consumo_router", "pendencias_router"]
