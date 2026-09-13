"""Camada de provedores de LLM do Shogun."""

from app.core.llm.aquecimento import aquecer_provider
from app.core.llm.base import (
    ACOES,
    DICA_ESQUEMA,
    ESQUEMA_COMANDO,
    SYSTEM_PROMPT,
    Acao,
    ComandoInterpretado,
    ConfiguracaoInvalidaError,
    LLMIndisponivelError,
    LLMProvider,
    UsoTokens,
    parsear_comando,
)
from app.core.llm.claude import ClaudeProvider
from app.core.llm.deterministico import DeterministicoProvider
from app.core.llm.fallback import FallbackLLMProvider
from app.core.llm.ollama import OllamaProvider
from app.core.llm.openai_compat import (
    DeepSeekProvider,
    OpenAICompatProvider,
    OpenAIMiniProvider,
)
from app.core.llm.registry import (
    PROVEDORES_SEM_REGISTRO_DE_USO,
    PROVIDERS,
    ProviderDesconhecidoError,
    criar_provider,
    get_llm_provider,
    montar_provider,
)

__all__ = [
    "ACOES",
    "DICA_ESQUEMA",
    "ESQUEMA_COMANDO",
    "PROVEDORES_SEM_REGISTRO_DE_USO",
    "PROVIDERS",
    "SYSTEM_PROMPT",
    "Acao",
    "ClaudeProvider",
    "ComandoInterpretado",
    "ConfiguracaoInvalidaError",
    "DeepSeekProvider",
    "DeterministicoProvider",
    "FallbackLLMProvider",
    "LLMIndisponivelError",
    "LLMProvider",
    "OllamaProvider",
    "OpenAICompatProvider",
    "OpenAIMiniProvider",
    "ProviderDesconhecidoError",
    "UsoTokens",
    "aquecer_provider",
    "criar_provider",
    "get_llm_provider",
    "montar_provider",
    "parsear_comando",
]
