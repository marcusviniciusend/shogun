"""Entrypoint do servidor central do Shogun."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import comando_router
from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not settings.anthropic_api_key:
        logger.warning("ANTHROPIC_API_KEY nao configurada - /comando respondera 503.")
    if not settings.shogun_auth_token:
        logger.warning("SHOGUN_AUTH_TOKEN vazio - servidor SEM autenticacao.")
    yield


app = FastAPI(title="Shogun Server", version="0.1.0", lifespan=lifespan)
app.include_router(comando_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
