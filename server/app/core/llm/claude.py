"""Provedor Claude (Anthropic) — implementação de referência do LLMProvider."""

import anthropic

from app.core.config import Settings
from app.core.llm.base import (
    ESQUEMA_COMANDO,
    SYSTEM_PROMPT,
    ComandoInterpretado,
    LLMIndisponivelError,
    parsear_comando,
)


class ClaudeProvider:
    """Interpreta comandos com a API da Anthropic e structured output nativo."""

    nome = "claude"

    def __init__(self, config: Settings) -> None:
        self._config = config
        self._client = (
            anthropic.AsyncAnthropic(api_key=config.anthropic_api_key)
            if config.anthropic_api_key
            else None
        )

    @property
    def configurado(self) -> bool:
        return self._client is not None

    async def interpretar_comando(self, texto: str) -> ComandoInterpretado:
        if self._client is None:
            raise LLMIndisponivelError(
                "ANTHROPIC_API_KEY não configurada — defina-a no .env do servidor."
            )

        try:
            resposta = await self._client.messages.create(
                model=self._config.shogun_model,
                max_tokens=self._config.shogun_max_tokens,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": texto}],
                output_config={
                    "format": {"type": "json_schema", "schema": ESQUEMA_COMANDO}
                },
            )
        except anthropic.AnthropicError as exc:  # rede, timeout, rate limit, 4xx/5xx
            raise LLMIndisponivelError(f"Anthropic: {exc}") from exc

        if resposta.stop_reason == "refusal":
            detalhe = getattr(resposta.stop_details, "explanation", None)
            raise LLMIndisponivelError(detalhe or "Pedido recusado pelo modelo.")
        if resposta.stop_reason == "max_tokens":
            raise LLMIndisponivelError(
                "Resposta truncada por max_tokens — aumente SHOGUN_MAX_TOKENS."
            )

        texto_json = next(
            (bloco.text for bloco in resposta.content if bloco.type == "text"), None
        )
        if texto_json is None:
            raise LLMIndisponivelError("Resposta da Claude sem conteúdo de texto.")

        return parsear_comando(texto_json)
