"""Entrypoint do servidor central do Shogun."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import comando_router
from app.core.config import settings
from app.core.llm import get_llm_provider
from app.core.rede import descobrir_bind

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Antes de qualquer outra coisa: nao subir aberto para a rede sem token.
    # O bind vem do uvicorn, nao do .env — `uvicorn --host 0.0.0.0` com
    # SHOGUN_HOST=127.0.0.1 tem que ser barrado do mesmo jeito. Fica no
    # lifespan, e nao so em run(), para valer tambem quando o servidor e
    # iniciado pela CLI do uvicorn, que nao passa por run().
    bind = descobrir_bind(settings.shogun_host)
    settings.validar_exposicao(bind)
    logger.info("Bind efetivo: %s", bind)

    provider = get_llm_provider()
    logger.info("Provedor de LLM ativo: %s", provider.nome)
    if not provider.configurado:
        logger.warning(
            "Nenhuma credencial de LLM configurada - /comando respondera 503."
        )
    if not settings.shogun_auth_token:
        # So chega aqui em bind local — validar_exposicao() ja barrou o resto.
        logger.warning(
            "SHOGUN_AUTH_TOKEN vazio - servidor SEM autenticacao, escutando "
            "apenas em %s.",
            bind.host,
        )
    yield


app = FastAPI(title="Shogun Server", version="0.1.0", lifespan=lifespan)

# CORS so entra quando ha origem configurada. Sem origens, o middleware nao e
# registrado: os clientes desktop e mobile falam HTTP direto, sem origem de
# navegador, e adicionar o middleware nao mudaria nada para eles.
if settings.allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(comando_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


def run() -> None:
    """Sobe o servidor no host/porta da configuracao.

    Existe para que `SHOGUN_HOST` e `SHOGUN_PORT` valham tambem quando o
    servidor e iniciado sem passar as flags do uvicorn na mao — o default
    do uvicorn e 127.0.0.1, que deixaria os clientes remotos de fora.
    """
    import uvicorn

    # Falha cedo, com mensagem limpa, antes de o uvicorn abrir a porta.
    settings.validar_exposicao()

    logger.info(
        "Escutando em http://%s:%s", settings.shogun_host, settings.shogun_port
    )
    uvicorn.run(app, host=settings.shogun_host, port=settings.shogun_port)


if __name__ == "__main__":
    run()
