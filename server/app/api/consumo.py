"""Rota GET /consumo — tokens gastos, custo real e comparativo entre provedores.

Contrato só do servidor (nenhum cliente o consome ainda), por isso os modelos
de resposta vivem aqui e não em `shared/`.
"""

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.core.config import Settings
from app.core.llm.precos import PRECOS, custo_usd
from app.core.llm.registry import PROVEDORES_SEM_REGISTRO_DE_USO
from app.core.persistencia import RepositorioConversas, get_repositorio
from app.core.rate_limit import limitar_leitura
from app.core.security import get_settings, require_auth

router = APIRouter(
    tags=["consumo"],
    dependencies=[Depends(require_auth), Depends(limitar_leitura)],
)


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


#: Por que `FallbackOut.taxa` veio nula. Códigos, não frase — quem consome
#: decide como mostrar, e o motivo não muda de texto sem quebrar o contrato.
MotivoSemTaxa = Literal[
    #: `SHOGUN_LLM_FALLBACK_PROVIDER` está vazio: não existe reserva para medir.
    "sem_reserva_configurada",
    #: Nenhuma mensagem do par (principal, reserva) no período — denominador zero.
    "sem_mensagens_do_par",
    #: Principal ou reserva não gravam uso (ver `PROVEDORES_SEM_REGISTRO_DE_USO`):
    #: a contagem seria cega e o zero resultante mentiria.
    "provedor_nao_registra_uso",
]


class FallbackOut(BaseModel):
    """Com que frequência o provedor reserva atendeu — leitura DESCRITIVA.

    A regra prática de `docs/CONTEXTO-GERAL.md` (4.2) para avaliar o modelo
    local é "rodar com fallback ligado e medir a frequência com que ele é
    acionado". Este bloco é essa medida, derivada de `messages_uso`: cada linha
    guarda o provedor que de fato respondeu, e o `FallbackLLMProvider` não
    sobrescreve esse nome. Nada é estimado e nada é gravado a mais.

    **A ressalva que este bloco NÃO pode esconder:** o banco registra quem
    respondeu, nunca quem estava *configurado* como principal na hora. Já
    `principal_configurado` e `reserva_configurada` vêm do ambiente de AGORA.
    Se a configuração mudou dentro da janela consultada (e `/consumo` aceita
    janela), os rótulos descrevem o hoje e as contagens descrevem o então — daí
    a resposta dizer "estas mensagens foram atendidas por X, e X é o principal
    configurado hoje", e não "X era o principal o período inteiro".

    `mensagens_outros` é o sinal dessa divergência: mensagem atendida por
    provedor que não é nem o principal nem o reserva de hoje só existe se a
    configuração já foi outra (ou se outro provedor escreveu no banco). Maior
    que zero, a taxa vale para o par de hoje e não para o período inteiro —
    fica descritiva, e é assim que deve ser lida.
    """

    #: `SHOGUN_LLM_PROVIDER` como está AGORA — não necessariamente no período.
    principal_configurado: str
    #: `SHOGUN_LLM_FALLBACK_PROVIDER` agora; `None` quando não há fallback.
    reserva_configurada: str | None
    #: Mensagens do período atendidas por cada um; `outros` = nem um nem outro.
    mensagens_principal: int
    mensagens_reserva: int
    mensagens_outros: int
    #: reserva / (principal + reserva), 0.0–1.0. `None` quando não dá para
    #: calcular honestamente — o motivo vem em `motivo_sem_taxa`.
    taxa: float | None
    #: `None` exatamente quando `taxa` não é `None`.
    motivo_sem_taxa: MotivoSemTaxa | None


class ConsumoResponse(BaseModel):
    inicio: datetime | None
    fim: datetime | None
    total_input_tokens: int
    total_output_tokens: int
    #: Soma do custo por provedor realmente usado em cada mensagem.
    custo_real_usd: float
    por_provider: list[ConsumoProviderOut]
    comparativo: list[ComparativoOut]
    fallback: FallbackOut


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

# A taxa é uma fração de 0 a 1; 4 casas descem à décima de ponto percentual,
# resolução de sobra para "o reserva atendeu 3,7% das mensagens".
_CASAS_TAXA = 4


def _resumir_fallback(linhas, config: Settings) -> FallbackOut:
    """Deriva o bloco `fallback` das linhas já agregadas por provedor.

    Reaproveita a mesma consulta de `por_provider` — a taxa não custa ida
    nenhuma a mais ao banco, é releitura do que já veio.

    Toda a honestidade do bloco está em quando a taxa **não** é calculada; ver
    a docstring de :class:`FallbackOut` para o que os números descrevem e o que
    não descrevem.
    """
    principal = config.shogun_llm_provider
    reserva = config.shogun_llm_fallback_provider.strip() or None
    # Mesma regra de `montar_provider`: reserva igual ao principal é ignorada,
    # e o provedor montado nem chega a ser um FallbackLLMProvider.
    if reserva == principal:
        reserva = None

    mensagens = {linha.provider: linha.mensagens for linha in linhas}
    do_principal = mensagens.get(principal, 0)
    do_reserva = mensagens.get(reserva, 0) if reserva else 0
    total = sum(mensagens.values())

    motivo: MotivoSemTaxa | None = None
    if reserva is None:
        motivo = "sem_reserva_configurada"
    elif {principal, reserva} & PROVEDORES_SEM_REGISTRO_DE_USO:
        # Zero linhas de um provedor que nunca grava uso não significa zero
        # acionamentos — significa ausência de registro. Melhor não responder.
        motivo = "provedor_nao_registra_uso"
    elif do_principal + do_reserva == 0:
        motivo = "sem_mensagens_do_par"

    return FallbackOut(
        principal_configurado=principal,
        reserva_configurada=reserva,
        mensagens_principal=do_principal,
        mensagens_reserva=do_reserva,
        mensagens_outros=total - do_principal - do_reserva,
        taxa=(
            None
            if motivo is not None
            else round(do_reserva / (do_principal + do_reserva), _CASAS_TAXA)
        ),
        motivo_sem_taxa=motivo,
    )


@router.get("/consumo", response_model=ConsumoResponse)
async def consultar_consumo(
    inicio: datetime | None = None,
    fim: datetime | None = None,
    repo: RepositorioConversas = Depends(get_repositorio),
    config: Settings = Depends(get_settings),
) -> ConsumoResponse:
    """Consumo agregado no período. Sem parâmetros = tudo desde o início.

    `inicio` é inclusivo e `fim` exclusivo, em ISO 8601 (UTC quando sem
    offset). O custo real usa o provedor que atendeu cada mensagem; o
    comparativo aplica o volume total ao preço de cada provedor da tabela.

    O bloco `fallback` responde "com que frequência o reserva atendeu" e é
    **descritivo**: as contagens vêm do banco (quem respondeu de fato), mas os
    nomes `principal_configurado`/`reserva_configurada` vêm do ambiente de
    agora — leia a docstring de :class:`FallbackOut` antes de tratar a taxa
    como característica do período inteiro.
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
        fallback=_resumir_fallback(linhas, config),
    )
