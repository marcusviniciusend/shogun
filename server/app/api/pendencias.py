"""Rota GET /pendencias — consulta direta, sem passar pelo LLM.

Existe para o painel de agentes dos clientes: saber o que esta pendente e uma
leitura estruturada, nao um comando de voz. Antes dela, a unica forma era o
POST /comando com a acao consultar_pendencias — uma chamada de LLM inteira (com
custo e latencia de modelo) para obter dados que o servidor ja tem na mao.

A rota depende da interface `PendenciasProvider`, nunca de implementacao
concreta — a troca acontece na injecao de dependencia, como no /comando.

O contrato da resposta vive em `shared/` (promovido quando o desktop passou a
consumir tipado): `PendenciaOut` e o espelho de fio do modelo de dominio
`Pendencia` — a conversao explicita aqui e o unico ponto onde os dois se
encontram.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from starlette.concurrency import run_in_threadpool

from app.core.contracts import PendenciaOut, PendenciasResponse
from app.core.pendencias import PendenciasProvider, get_pendencias_provider
from app.core.rate_limit import limitar_leitura
from app.core.security import require_auth
from app.domain import Pendencia

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["pendencias"],
    dependencies=[Depends(require_auth), Depends(limitar_leitura)],
)

#: Detalhe do 503 quando o provedor falha.
#:
#: Generico e estavel de proposito: a mensagem crua da excecao carrega caminho
#: de arquivo, driver de banco e URL de provedor externo. O detalhe real fica
#: no `logger.exception` abaixo, no servidor.
_DETALHE_FALHA_PROVEDOR = "Nao consegui consultar as pendencias agora."


def _como_pendencia_out(pendencia: Pendencia) -> PendenciaOut:
    return PendenciaOut(
        agente_id=pendencia.agente_id,
        agente_nome=pendencia.agente_nome,
        status=pendencia.status.value,
        descricao=pendencia.descricao,
        timestamp=pendencia.timestamp,
        prioridade=pendencia.prioridade,
    )


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
            detail=_DETALHE_FALHA_PROVEDOR,
        ) from exc

    pendencias.sort(key=lambda p: (-p.prioridade, p.timestamp))
    return PendenciasResponse(
        total=len(pendencias),
        pendencias=[_como_pendencia_out(p) for p in pendencias],
    )
