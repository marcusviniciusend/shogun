"""Rotas GET /sessoes e GET /sessoes/{id}/mensagens — historico de conversas.

Motivo: o session_id persistido no cliente tornava a conversa eterna. Com o
historico exposto, o cliente pode comecar conversa nova (mandando session_id
nulo no /comando) e reabrir as antigas.

O shape das respostas e CONTRATO COMBINADO com o desktop, que desenvolve
contra ele em paralelo — mudanca aqui exige combinar de novo:

    GET /sessoes
    {"total": N, "sessoes": [{"id", "criada_em", "atualizada_em",
                              "titulo", "total_mensagens"}]}

    GET /sessoes/{id}/mensagens
    {"session_id": "...", "mensagens": [{"autor": "usuario"|"shogun",
                                         "texto", "criada_em"}]}

Modelos na propria rota, como o precedente do /consumo: promove-se a shared/
quando um cliente tipado consumir via contrato gerado.
"""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.core.persistencia import RepositorioConversas, get_repositorio
from app.core.rate_limit import limitar_leitura
from app.core.security import require_auth
from app.db.models import ROLE_USUARIO
from app.db.repositorio import SessaoResumo

router = APIRouter(
    tags=["sessoes"],
    dependencies=[Depends(require_auth), Depends(limitar_leitura)],
)

#: Palavras da primeira fala do usuario que viram titulo da sessao.
_PALAVRAS_TITULO = 6

#: Titulo de sessao sem nenhuma fala do usuario (ex.: comando que falhou no
#: LLM antes da resposta) — o cliente sempre recebe algo exibivel.
_TITULO_VAZIO = "(conversa vazia)"


class SessaoOut(BaseModel):
    id: str
    criada_em: datetime
    atualizada_em: datetime
    titulo: str
    total_mensagens: int


class SessoesResponse(BaseModel):
    total: int
    sessoes: list[SessaoOut]


class MensagemOut(BaseModel):
    autor: Literal["usuario", "shogun"]
    texto: str
    criada_em: datetime


class MensagensResponse(BaseModel):
    session_id: str
    mensagens: list[MensagemOut]


def _titulo(primeira_mensagem: str | None) -> str:
    """As primeiras palavras da primeira fala do usuario, com reticencia.

    Derivado na leitura, sem coluna nova: o dado ja esta em `messages`, e um
    titulo materializado poderia divergir dele.
    """
    if primeira_mensagem is None:
        return _TITULO_VAZIO
    palavras = primeira_mensagem.split()
    titulo = " ".join(palavras[:_PALAVRAS_TITULO])
    if len(palavras) > _PALAVRAS_TITULO:
        titulo += "…"
    return titulo or _TITULO_VAZIO


def _como_sessao_out(resumo: SessaoResumo) -> SessaoOut:
    return SessaoOut(
        id=resumo.id,
        criada_em=resumo.criada_em,
        atualizada_em=resumo.atualizada_em,
        titulo=_titulo(resumo.primeira_mensagem_usuario),
        total_mensagens=resumo.total_mensagens,
    )


@router.get("/sessoes", response_model=SessoesResponse)
async def listar_sessoes(
    repo: RepositorioConversas = Depends(get_repositorio),
) -> SessoesResponse:
    """Todas as sessoes, da mais recentemente ativa para a mais antiga."""
    # Repositorio sincrono na threadpool, como /comando e /consumo.
    resumos = await run_in_threadpool(repo.listar_sessoes)
    return SessoesResponse(
        total=len(resumos), sessoes=[_como_sessao_out(r) for r in resumos]
    )


def _mensagens_da_sessao(repo: RepositorioConversas, session_id: str):
    """Existencia + historico numa ida so a threadpool. `None` = sessao nao existe."""
    if repo.obter_sessao(session_id) is None:
        return None
    return repo.historico(session_id)


@router.get("/sessoes/{session_id}/mensagens", response_model=MensagensResponse)
async def listar_mensagens(
    session_id: str,
    repo: RepositorioConversas = Depends(get_repositorio),
) -> MensagensResponse:
    """As mensagens de uma sessao, em ordem cronologica."""
    mensagens = await run_in_threadpool(_mensagens_da_sessao, repo, session_id)
    if mensagens is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sessao '{session_id}' nao existe.",
        )
    return MensagensResponse(
        session_id=session_id,
        mensagens=[
            MensagemOut(
                autor="usuario" if m.role == ROLE_USUARIO else "shogun",
                texto=m.content,
                criada_em=m.created_at,
            )
            for m in mensagens
        ],
    )
