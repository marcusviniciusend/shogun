"""Rota GET /consumo — tokens gastos, custo real e comparativo entre provedores.

Contrato só do servidor (nenhum cliente o consome ainda), por isso os modelos
de resposta vivem aqui e não em `shared/`.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.core.llm.precos import PRECOS, custo_usd
from app.core.persistencia import RepositorioConversas, get_repositorio
from app.core.security import require_auth

router = APIRouter(tags=["consumo"], dependencies=[Depends(require_auth)])


class ConsumoProviderOut(BaseModel):
    """O que foi gasto de fato num provedor dentro do período."""

    provider: str
    mensagens: int
    input_tokens: int
    output_tokens: int
    custo_usd: float


class ComparativoOut(BaseModel):
    """Quanto o volume TOTAL do período custaria se fosse todo deste provedor."""

    provider: str
    custo_usd: float


class ConsumoResponse(BaseModel):
    inicio: datetime | None
    fim: datetime | None
    total_input_tokens: int
    total_output_tokens: int
    #: Soma do custo por provedor realmente usado em cada mensagem.
    custo_real_usd: float
    por_provider: list[ConsumoProviderOut]
    comparativo: list[ComparativoOut]


def _para_utc_naive(momento: datetime | None) -> datetime | None:
    """Normaliza a data da query para o formato interno (UTC sem tzinfo).

    O banco grava UTC naive (ver `docs/DATABASE.md`); uma data com offset na
    query string seria comparada errada se entrasse crua.
    """
    if momento is None or momento.tzinfo is None:
        return momento
    return momento.astimezone(timezone.utc).replace(tzinfo=None)


# Centavos de dólar têm 2 casas; 6 dá margem para tokens avulsos de modelos
# baratos sem devolver ruído de ponto flutuante no JSON.
_CASAS = 6


@router.get("/consumo", response_model=ConsumoResponse)
async def consultar_consumo(
    inicio: datetime | None = None,
    fim: datetime | None = None,
    repo: RepositorioConversas = Depends(get_repositorio),
) -> ConsumoResponse:
    """Consumo agregado no período. Sem parâmetros = tudo desde o início.

    `inicio` é inclusivo e `fim` exclusivo, em ISO 8601 (UTC quando sem
    offset). O custo real usa o provedor que atendeu cada mensagem; o
    comparativo aplica o volume total ao preço de cada provedor da tabela.
    """
    inicio = _para_utc_naive(inicio)
    fim = _para_utc_naive(fim)

    linhas = await run_in_threadpool(repo.consumo_por_provider, inicio, fim)

    por_provider = [
        ConsumoProviderOut(
            provider=linha.provider,
            mensagens=linha.mensagens,
            input_tokens=linha.input_tokens,
            output_tokens=linha.output_tokens,
            custo_usd=round(
                custo_usd(linha.provider, linha.input_tokens, linha.output_tokens),
                _CASAS,
            ),
        )
        for linha in sorted(linhas, key=lambda l: l.provider)
    ]

    total_input = sum(linha.input_tokens for linha in linhas)
    total_output = sum(linha.output_tokens for linha in linhas)

    return ConsumoResponse(
        inicio=inicio,
        fim=fim,
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        custo_real_usd=round(sum(item.custo_usd for item in por_provider), _CASAS),
        por_provider=por_provider,
        # Todos os provedores da tabela, inclusive o(s) realmente usado(s):
        # assim o comparativo fica completo e a ordem não depende de quem
        # atendeu o período.
        comparativo=[
            ComparativoOut(
                provider=nome,
                custo_usd=round(custo_usd(nome, total_input, total_output), _CASAS),
            )
            for nome in sorted(PRECOS)
        ],
    )
