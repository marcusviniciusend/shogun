"""Registro de provedores e factory usada na injeção de dependências.

Para adicionar um provedor novo: crie a classe implementando ``LLMProvider`` e
acrescente uma entrada em :data:`PROVIDERS`. Nada mais precisa mudar — nem a
factory, nem as rotas.
"""

import logging
from functools import lru_cache

from app.core.config import Settings, settings
from app.core.llm.base import LLMProvider
from app.core.llm.claude import ClaudeProvider
from app.core.llm.fallback import FallbackLLMProvider
from app.core.llm.openai_compat import DeepSeekProvider, OpenAIMiniProvider

logger = logging.getLogger(__name__)

#: Nome de configuração -> classe do provedor. Todo provedor recebe ``Settings``
#: no construtor; é esse contrato uniforme que torna o registro extensível.
PROVIDERS: dict[str, type[LLMProvider]] = {
    "claude": ClaudeProvider,
    "deepseek": DeepSeekProvider,
    "openai_mini": OpenAIMiniProvider,
}


class ProviderDesconhecidoError(ValueError):
    """O nome configurado não existe em :data:`PROVIDERS`."""


def criar_provider(nome: str, config: Settings) -> LLMProvider:
    """Instancia um provedor pelo nome registrado."""
    try:
        classe = PROVIDERS[nome]
    except KeyError as exc:
        disponiveis = ", ".join(sorted(PROVIDERS))
        raise ProviderDesconhecidoError(
            f"Provedor de LLM '{nome}' desconhecido. Disponíveis: {disponiveis}."
        ) from exc
    return classe(config)


def montar_provider(config: Settings) -> LLMProvider:
    """Monta o provedor principal, envolto em fallback quando configurado."""
    principal = criar_provider(config.shogun_llm_provider, config)

    reserva_nome = config.shogun_llm_fallback_provider.strip()
    if not reserva_nome:
        return principal
    if reserva_nome == config.shogun_llm_provider:
        logger.warning(
            "SHOGUN_LLM_FALLBACK_PROVIDER igual ao principal ('%s') — ignorado.",
            reserva_nome,
        )
        return principal

    return FallbackLLMProvider(principal, criar_provider(reserva_nome, config))


@lru_cache(maxsize=1)
def _provider_cacheado() -> LLMProvider:
    return montar_provider(settings)


def get_llm_provider() -> LLMProvider:
    """Dependência do FastAPI — sobrescrita via ``app.dependency_overrides``."""
    return _provider_cacheado()
