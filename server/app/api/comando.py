"""Rota POST /comando — ponto de entrada dos clientes desktop e mobile."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from starlette.concurrency import run_in_threadpool

from app.core.contracts import (
    AgentAction,
    ClientInstruction,
    CommandRequest,
    CommandResponse,
)
from app.core.config import settings
from app.core.llm import (
    ComandoInterpretado,
    LLMIndisponivelError,
    LLMProvider,
    UsoTokens,
    get_llm_provider,
)
from app.core.llm.historico import montar_prompt
from app.core.persistencia import RepositorioConversas, get_repositorio
from app.core.pendencias import PendenciasProvider, get_pendencias_provider
from app.core.rate_limit import limitar_comando
from app.core.security import require_auth
from app.domain import Pendencia, StatusAgente

logger = logging.getLogger(__name__)


def _abrir_conversa(
    repo: RepositorioConversas, session_id: str | None, texto: str, janela: int
) -> tuple[str, list[tuple[str, str]]]:
    """Prepara a conversa para a chamada ao LLM. Devolve `(id, historico)`.

    Junta os tres acessos ao banco desta etapa numa funcao so — a rota paga uma
    ida a threadpool, nao tres.

    O historico e lido **antes** do INSERT da mensagem nova, senao o comando
    atual apareceria duas vezes no prompt: uma no bloco de contexto e outra no
    fim. E o INSERT acontece **antes** da chamada ao modelo, para que um comando
    que falhe no LLM continue registrado — o passo 5 pode devolver 503, e nesse
    caso a pergunta do Marcus nao pode sumir do historico.
    """
    sessao = repo.obter_ou_criar_sessao(session_id)
    historico = [
        (m.role, m.content) for m in repo.historico(sessao.id, limite=janela)
    ]
    repo.registrar_usuario(sessao.id, texto)
    return sessao.id, historico


def _fechar_conversa(
    repo: RepositorioConversas,
    session_id: str,
    resposta: str,
    uso: UsoTokens | None,
) -> None:
    """Grava a fala do Shogun e marca atividade na sessao (passo 8).

    Quando o provedor reportou consumo, ele e gravado junto, amarrado a
    mensagem do assistente — e o que alimenta o GET /consumo.
    """
    mensagem = repo.registrar_assistente(session_id, resposta)
    if uso is not None:
        repo.registrar_uso(
            mensagem.id, uso.provider, uso.input_tokens, uso.output_tokens
        )
    sessao = repo.obter_sessao(session_id)
    if sessao is not None:
        repo.marcar_atividade(sessao)


router = APIRouter(
    tags=["comando"],
    # Ordem importa: autenticacao primeiro — token invalido vira 401 sem
    # consumir cota do rate limit.
    dependencies=[Depends(require_auth), Depends(limitar_comando)],
)


# Estados que merecem destaque na fala: são pendências que estão travando algo.
_STATUS_CRITICOS = frozenset({StatusAgente.TRAVADO, StatusAgente.ERRO})

#: Detalhe devolvido ao cliente quando o provedor de pendências falha.
#:
#: Genérico e estável de propósito: a mensagem crua da exceção carrega caminho
#: de arquivo, driver de banco e URL de provedor externo — coisas que o cliente
#: não precisa e que não devem sair do servidor. O detalhe real fica no
#: `logger.exception` de quem tratou a falha.
_DETALHE_FALHA_PROVEDOR = "provedor de pendências indisponível"

#: Mesma ideia para o LLM: o cliente sabe que o Shogun não pensou, não *por que*
#: — a mensagem do provedor (endpoint, modelo, resposta crua) fica no log.
_DETALHE_LLM_INDISPONIVEL = (
    "Não consegui pensar agora, Marcus. Tente de novo em instantes."
)


def _descrever(pendencia: Pendencia) -> str:
    """Uma pendência em uma frase curta, do jeito que o Shogun falaria."""
    texto = f"{pendencia.descricao} ({pendencia.agente_nome}"
    if pendencia.status in _STATUS_CRITICOS:
        texto += f", {pendencia.status.value}"
    return texto + ")"


async def _consultar_pendencias(
    intencao: ComandoInterpretado, provider: PendenciasProvider
) -> tuple[str, AgentAction]:
    """Executa a ação ``consultar_pendencias`` usando o provedor injetado."""
    try:
        # get_pendencias_agentes() é síncrono e pode fazer I/O (ex.: MaestriProvider
        # chama a API do Maestri), então vai para a threadpool para não bloquear
        # o event loop enquanto outros comandos são atendidos.
        pendencias = list(await run_in_threadpool(provider.get_pendencias_agentes))
    except Exception:  # provedor externo: nunca derruba o comando
        logger.exception("Falha ao consultar pendências")
        return (
            "Não consegui consultar suas pendências agora.",
            AgentAction(
                agent="pendencias",
                status="error",
                detail=_DETALHE_FALHA_PROVEDOR,
            ),
        )

    if not pendencias:
        return (
            "Nenhuma pendência registrada, Marcus.",
            AgentAction(agent="pendencias", status="ok", detail="0 pendências"),
        )

    # O contrato não promete ordem; as mais urgentes vêm primeiro na fala.
    pendencias.sort(key=lambda p: (-p.prioridade, p.timestamp))

    # `limite` não faz parte de get_pendencias_agentes(), então é aplicado aqui:
    # serve para o Marcus pedir "as três mais urgentes" sem estourar a fala.
    total = len(pendencias)
    limite = intencao.parametros.get("limite")
    if isinstance(limite, int) and 0 < limite < total:
        pendencias = pendencias[:limite]

    itens = "; ".join(_descrever(p) for p in pendencias)
    plural = "pendência" if total == 1 else "pendências"
    fala = f"Você tem {total} {plural}: {itens}."
    if len(pendencias) < total:
        fala = (
            f"Você tem {total} {plural}. As {len(pendencias)} mais urgentes: {itens}."
        )

    return (
        fala,
        AgentAction(agent="pendencias", status="ok", detail=f"{total} pendências"),
    )


def _abrir_app(intencao: ComandoInterpretado) -> tuple[str, AgentAction]:
    """Delegação da ação ``abrir_app`` ao cliente.

    O servidor pode rodar em outra máquina e não tem acesso ao SO do usuário:
    quem abre o app é o cliente, seguindo a `ClientInstruction` dentro da
    `AgentAction`. Cliente que ainda não executa instruções apenas exibe a
    action como metadado; cliente que não suporta o app pedido responde com
    `fallback_text`. Nada é executado aqui.
    """
    app_alvo = str(intencao.parametros.get("app", "")).strip()
    if not app_alvo:
        return (
            "Não entendi qual aplicativo abrir, Marcus — pode repetir com o nome dele?",
            AgentAction(
                agent="sistema", status="error", detail="abrir_app sem parâmetro app"
            ),
        )
    instrucao = ClientInstruction(
        type="open_app",
        app=app_alvo,
        fallback_text=f"Não consegui abrir o {app_alvo} neste aparelho, Marcus.",
    )
    return (
        f"Pedi para este aparelho abrir o {app_alvo}, Marcus.",
        AgentAction(
            agent="sistema",
            status="ok",
            detail=f"execução delegada ao cliente (app={app_alvo})",
            instruction=instrucao,
        ),
    )


@router.post("/comando", response_model=CommandResponse)
async def processar_comando(
    comando: CommandRequest,
    llm: LLMProvider = Depends(get_llm_provider),
    pendencias: PendenciasProvider = Depends(get_pendencias_provider),
    repo: RepositorioConversas = Depends(get_repositorio),
) -> CommandResponse:
    """Recebe o texto já transcrito, interpreta a intenção e executa a ação."""
    texto = comando.text.strip()
    if not texto:
        # Antes de qualquer escrita: comando vazio não abre sessão nem entra no
        # histórico.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Comando vazio.",
        )

    # SQLAlchemy síncrono na threadpool, como o PendenciasProvider — o event
    # loop segue livre enquanto o banco responde.
    session_id, historico = await run_in_threadpool(
        _abrir_conversa,
        repo,
        comando.session_id,
        texto,
        settings.shogun_historico_max_mensagens,
    )

    try:
        intencao = await llm.interpretar_comando(montar_prompt(historico, texto))
    except LLMIndisponivelError as exc:
        logger.error("LLM indisponível: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_DETALHE_LLM_INDISPONIVEL,
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

    await run_in_threadpool(
        _fechar_conversa, repo, session_id, resposta, intencao.uso
    )

    # `session_id` vem da sessão, não do request: quando o cliente manda nulo,
    # é aqui que ele descobre qual conversa o servidor abriu.
    return CommandResponse(session_id=session_id, text=resposta, actions=acoes)
