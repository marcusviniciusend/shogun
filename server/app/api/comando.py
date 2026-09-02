"""Rota POST /comando — ponto de entrada dos clientes desktop e mobile."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.claude import (
    ClaudeClient,
    ClaudeIndisponivelError,
    Intencao,
    get_claude_client,
)
from app.core.contracts import AgentAction, CommandRequest, CommandResponse
from app.core.pendencias import PendenciasProvider, get_pendencias_provider
from app.core.security import require_auth

logger = logging.getLogger(__name__)

router = APIRouter(tags=["comando"], dependencies=[Depends(require_auth)])


async def _consultar_pendencias(
    intencao: Intencao, provider: PendenciasProvider
) -> tuple[str, AgentAction]:
    """Executa a ação ``consultar_pendencias`` usando o provedor injetado."""
    limite = intencao.parametros.get("limite", 10)
    limite = limite if isinstance(limite, int) and limite > 0 else 10

    try:
        pendencias = await provider.listar_pendencias(limite=limite)
    except Exception as exc:  # provedor externo: nunca derruba o comando
        logger.exception("Falha ao consultar pendências")
        return (
            "Não consegui consultar suas pendências agora.",
            AgentAction(agent="pendencias", status="error", detail=str(exc)),
        )

    if not pendencias:
        # Distingue "nada pendente" de "fonte ainda não conectada", para não
        # afirmar ao Marcus que ele está em dia quando na verdade não sabemos.
        if not getattr(provider, "disponivel", True):
            return (
                "A fonte de pendências ainda não está conectada, Marcus.",
                AgentAction(
                    agent="pendencias",
                    status="error",
                    detail="Provedor de pendências não configurado.",
                ),
            )
        return (
            "Você não tem pendências no momento, Marcus.",
            AgentAction(agent="pendencias", status="ok", detail="0 pendências"),
        )

    itens = "; ".join(
        p.titulo if not p.prazo else f"{p.titulo} (até {p.prazo})" for p in pendencias
    )
    plural = "pendência" if len(pendencias) == 1 else "pendências"
    return (
        f"Você tem {len(pendencias)} {plural}: {itens}.",
        AgentAction(
            agent="pendencias", status="ok", detail=f"{len(pendencias)} pendências"
        ),
    )


def _abrir_app(intencao: Intencao) -> tuple[str, AgentAction]:
    """Placeholder da ação ``abrir_app``.

    TODO: o cliente (desktop/mobile) é quem tem acesso ao sistema operacional.
    O servidor deve devolver a ação e o cliente executa a abertura — definir esse
    contrato junto com o agente-desktop.
    """
    app_alvo = str(intencao.parametros.get("app", "")).strip()
    detalhe = f"abrir_app ainda não implementado (app={app_alvo or 'desconhecido'})"
    fala = (
        f"Ainda não consigo abrir o {app_alvo}, Marcus — essa ação está em construção."
        if app_alvo
        else "Ainda não consigo abrir aplicativos, Marcus — essa ação está em construção."
    )
    return fala, AgentAction(agent="sistema", status="error", detail=detalhe)


@router.post("/comando", response_model=CommandResponse)
async def processar_comando(
    comando: CommandRequest,
    claude: ClaudeClient = Depends(get_claude_client),
    pendencias: PendenciasProvider = Depends(get_pendencias_provider),
) -> CommandResponse:
    """Recebe o texto já transcrito, interpreta a intenção e executa a ação."""
    texto = comando.text.strip()
    if not texto:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Comando vazio.",
        )

    try:
        intencao = await claude.interpretar(texto)
    except ClaudeIndisponivelError as exc:
        logger.error("Claude indisponível: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Não consegui pensar agora: {exc}",
        ) from exc

    acoes: list[AgentAction] = []
    resposta = intencao.resposta_falada

    if intencao.acao == "consultar_pendencias":
        resposta, acao = await _consultar_pendencias(intencao, pendencias)
        acoes.append(acao)
    elif intencao.acao == "abrir_app":
        resposta, acao = _abrir_app(intencao)
        acoes.append(acao)
    # "conversar" usa a resposta livre do modelo, sem ação de agente.

    return CommandResponse(
        session_id=comando.session_id, text=resposta, actions=acoes
    )
