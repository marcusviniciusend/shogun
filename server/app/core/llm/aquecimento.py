"""Aquecimento do modelo local no startup do servidor.

Motivo: um modelo local frio leva mais de 30s para carregar, e
``SHOGUN_LLM_TIMEOUT`` e 30s — sem aquecimento, todo primeiro comando do dia
devolve 503 (item 4 do levantamento de resiliencia do desktop). Aquecer no
startup move o carregamento para antes do primeiro comando.

O aquecimento e OPCIONAL por provedor e fica fora do ``Protocol``
``LLMProvider`` de proposito: provedores de nuvem nao tem o que aquecer, e
exigir o metodo de todos seria mudanca de contrato sem beneficio. Quem oferece
aquecimento declara um ``async def aquecer()``; este modulo descobre por
``getattr`` e percorre o ``FallbackLLMProvider`` para alcancar principal e
reserva.

Falha de aquecimento NUNCA derruba nem atrasa o servidor: e otimizacao. Se o
Ollama estiver fora no boot, o log avisa e o fluxo normal (timeout + fallback)
continua valendo.
"""

import logging

from app.core.llm.base import LLMIndisponivelError, LLMProvider
from app.core.llm.fallback import FallbackLLMProvider

logger = logging.getLogger(__name__)


def _componentes(provider: LLMProvider) -> list[LLMProvider]:
    """Provedores concretos por tras de `provider`, desfazendo o fallback."""
    if isinstance(provider, FallbackLLMProvider):
        return _componentes(provider.principal) + _componentes(provider.reserva)
    return [provider]


async def aquecer_provider(provider: LLMProvider) -> None:
    """Aquece todo componente de `provider` que souber se aquecer.

    Percorre o wrapper de fallback e chama ``aquecer()`` onde o metodo existir.
    Erros sao logados e engolidos: o servidor sobe do mesmo jeito, so perde a
    otimizacao.
    """
    for componente in _componentes(provider):
        aquecer = getattr(componente, "aquecer", None)
        if aquecer is None:
            continue
        try:
            await aquecer()
        except LLMIndisponivelError as exc:
            logger.warning(
                "Aquecimento do provedor '%s' falhou (seguindo sem ele): %s",
                componente.nome,
                exc,
            )
        else:
            logger.info("Provedor '%s' aquecido.", componente.nome)
