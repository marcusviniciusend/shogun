"""Provedores que falam o protocolo de chat completions da OpenAI.

DeepSeek e OpenAI compartilham o mesmo formato de requisição, então a chamada
vive na classe base e cada provedor só declara o que é seu: credencial, modelo,
endpoint e como pede a saída estruturada.
"""

from typing import Any

from openai import AsyncOpenAI, OpenAIError

from app.core.config import Settings
from app.core.llm.base import (
    DICA_ESQUEMA,
    ESQUEMA_COMANDO,
    SYSTEM_PROMPT,
    ComandoInterpretado,
    LLMIndisponivelError,
    parsear_comando,
)


class OpenAICompatProvider:
    """Base para provedores compatíveis com a API de chat completions da OpenAI."""

    nome = "openai_compat"
    #: ``None`` usa o endpoint padrão da OpenAI.
    base_url: str | None = None

    def __init__(self, config: Settings) -> None:
        self._config = config
        self._modelo = self._model_id(config)
        chave = self._api_key(config)
        self._client = (
            AsyncOpenAI(
                api_key=chave,
                base_url=self.base_url,
                timeout=config.shogun_llm_timeout,
            )
            if chave
            else None
        )

    # --- a preencher por cada provedor ------------------------------------

    def _api_key(self, config: Settings) -> str:
        raise NotImplementedError

    def _model_id(self, config: Settings) -> str:
        raise NotImplementedError

    def _response_format(self) -> dict[str, Any]:
        """Como pedir JSON à API. Sobrescreva quando houver modo nativo melhor."""
        return {"type": "json_object"}

    def _system_prompt(self) -> str:
        """Prompt de sistema.

        A personalidade (``SYSTEM_PROMPT``) é sempre a mesma; provedores que não
        impõem o schema pela API recebem ``DICA_ESQUEMA`` como acréscimo.
        """
        return SYSTEM_PROMPT + DICA_ESQUEMA

    # --- fluxo comum -------------------------------------------------------

    @property
    def configurado(self) -> bool:
        return self._client is not None

    async def interpretar_comando(self, texto: str) -> ComandoInterpretado:
        if self._client is None:
            raise LLMIndisponivelError(
                f"Credencial do provedor '{self.nome}' não configurada."
            )

        try:
            resposta = await self._client.chat.completions.create(
                model=self._modelo,
                max_tokens=self._config.shogun_max_tokens,
                messages=[
                    {"role": "system", "content": self._system_prompt()},
                    {"role": "user", "content": texto},
                ],
                response_format=self._response_format(),
            )
        except OpenAIError as exc:  # rede, timeout, rate limit, 4xx/5xx
            raise LLMIndisponivelError(f"{self.nome}: {exc}") from exc

        if not resposta.choices:
            raise LLMIndisponivelError(f"{self.nome}: resposta sem choices.")

        escolha = resposta.choices[0]
        if getattr(escolha.message, "refusal", None):
            raise LLMIndisponivelError(escolha.message.refusal)
        if escolha.finish_reason == "length":
            raise LLMIndisponivelError(
                "Resposta truncada por max_tokens — aumente SHOGUN_MAX_TOKENS."
            )

        conteudo = escolha.message.content
        if not conteudo:
            raise LLMIndisponivelError(f"{self.nome}: resposta sem conteúdo.")

        return parsear_comando(conteudo)


class DeepSeekProvider(OpenAICompatProvider):
    """DeepSeek — API compatível com OpenAI, saída estruturada via JSON mode.

    O JSON mode do DeepSeek garante JSON sintaticamente válido, mas não impõe o
    schema; por isso o formato vai descrito no prompt e a validação final fica
    com o Pydantic em ``parsear_comando``.
    """

    nome = "deepseek"
    base_url = "https://api.deepseek.com"

    def _api_key(self, config: Settings) -> str:
        return config.deepseek_api_key

    def _model_id(self, config: Settings) -> str:
        return config.deepseek_model


class OpenAIMiniProvider(OpenAICompatProvider):
    """GPT-4o-mini via API da OpenAI, com structured output nativo (json_schema).

    O ``strict: true`` faz a própria API garantir o schema, então aqui o prompt
    de sistema é o ``SYSTEM_PROMPT`` puro, sem a dica de formato.
    """

    nome = "openai_mini"

    def _api_key(self, config: Settings) -> str:
        return config.openai_api_key

    def _model_id(self, config: Settings) -> str:
        return config.openai_mini_model

    def _response_format(self) -> dict[str, Any]:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "comando_shogun",
                "strict": True,
                "schema": ESQUEMA_COMANDO,
            },
        }

    def _system_prompt(self) -> str:
        return SYSTEM_PROMPT
