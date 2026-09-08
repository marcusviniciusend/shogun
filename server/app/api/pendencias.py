"""Rota GET /pendencias — consulta direta, sem passar pelo LLM.

Existe para o painel de agentes dos clientes: saber o que esta pendente e uma
leitura estruturada, nao um comando de voz. Antes dela, a unica forma era o
POST /comando com a acao consultar_pendencias — uma chamada de LLM inteira (com
custo e latencia de modelo) para obter dados que o servidor ja tem na mao.

A rota depende da interface `PendenciasProvider`, nunca de implementacao
concreta — a troca acontece na injecao de dependencia, como no /comando.

O shape da resposta reaproveita os modelos de dominio (`Pendencia`, com
`StatusAgente` dentro): a serializacao e direta, sem conversao manual. O
contrato e so do servidor por enquanto (como o /consumo); quando um cliente
tipado consumir, promove-se o modelo para `shared/` nas duas pontas.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.core.pendencias import PendenciasProvider, get_pendencias_provider
from app.core.rate_limit import limitar_leitura
from app.core.security import require_auth
from app.domain import Pendencia

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["pendencias"],
    dependencies=[Depends(require_auth), Depends(limitar_leitura)],
)


class PendenciasResponse(BaseModel):
    """Pendencias abertas, das mais urgentes para as menos."""

    total: int
    pendencias: list[Pendencia]


@router.get("/pendencias", response_model=PendenciasResponse)
async def listar_pendencias(
    provider: PendenciasProvider = Depends(get_pendencias_provider),
) -> PendenciasResponse:
    """Todas as pendencias abertas, ordenadas por urgencia.

    Mesma ordenacao da fala do /comando (prioridade decrescente, depois
    timestamp): o painel e a voz nao podem discordar sobre o que e mais
    urgente.
    """
    try:
        # Provedor sincrono e possivelmente com I/O (ex.: API do Maestri):
        # threadpool, como o /comando ja faz.
        pendencias = list(await run_in_threadpool(provider.get_pendencias_agentes))
    except Exception as exc:
        # No /comando a falha do provedor vira fala de desculpa; aqui o
        # consumidor e um programa, entao o erro precisa ser um status HTTP.
        logger.exception("Falha ao consultar pendencias")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Nao consegui consultar as pendencias: {exc}",
        ) from exc

    pendencias.sort(key=lambda p: (-p.prioridade, p.timestamp))
    return PendenciasResponse(total=len(pendencias), pendencias=pendencias)
