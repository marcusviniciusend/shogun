"""Cliente da API da Anthropic — interpreta comandos e devolve a intenção."""

import json
import logging
from functools import lru_cache
from typing import Any, Literal

import anthropic
from pydantic import BaseModel, Field, ValidationError

from app.core.config import Settings, settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Você é o Shogun, assistente pessoal de confiança do Marcus. Responda de forma "
    "direta e respeitosa, como um conselheiro. Interprete comandos e responda em "
    "JSON estruturado com: { acao: string, parametros: object, resposta_falada: string }"
)

Acao = Literal["conversar", "consultar_pendencias", "abrir_app"]

# Schema enviado à API para garantir que a resposta já venha no formato certo.
INTENCAO_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "acao": {
            "type": "string",
            "enum": ["conversar", "consultar_pendencias", "abrir_app"],
            "description": (
                "conversar = resposta livre; consultar_pendencias = o Marcus quer "
                "saber o que está pendente; abrir_app = abrir um aplicativo no "
                "dispositivo (parametros.app com o nome do app)."
            ),
        },
        "parametros": {
            "type": "object",
            "description": "Parâmetros da ação. Objeto vazio quando não houver.",
            "additionalProperties": True,
        },
        "resposta_falada": {
            "type": "string",
            "description": "Texto que será falado ao Marcus, em português do Brasil.",
        },
    },
    "required": ["acao", "parametros", "resposta_falada"],
    "additionalProperties": False,
}


class Intencao(BaseModel):
    """Interpretação estruturada de um comando."""

    acao: Acao = "conversar"
    parametros: dict[str, Any] = Field(default_factory=dict)
    resposta_falada: str


class ClaudeIndisponivelError(RuntimeError):
    """A API da Claude não pôde ser consultada."""


class ClaudeClient:
    """Wrapper fino sobre o SDK da Anthropic com o prompt de sistema do Shogun."""

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

    async def interpretar(
        self,
        texto: str,
        historico: list[dict[str, Any]] | None = None,
    ) -> Intencao:
        """Envia o comando à Claude e devolve a intenção já validada."""
        if self._client is None:
            raise ClaudeIndisponivelError(
                "ANTHROPIC_API_KEY não configurada — defina-a no .env do servidor."
            )

        mensagens: list[dict[str, Any]] = list(historico or [])
        mensagens.append({"role": "user", "content": texto})

        try:
            resposta = await self._client.messages.create(
                model=self._config.shogun_model,
                max_tokens=self._config.shogun_max_tokens,
                system=SYSTEM_PROMPT,
                messages=mensagens,
                output_config={
                    "format": {"type": "json_schema", "schema": INTENCAO_SCHEMA}
                },
            )
        except anthropic.APIError as exc:  # rede, rate limit, 4xx/5xx
            raise ClaudeIndisponivelError(str(exc)) from exc

        if resposta.stop_reason == "refusal":
            detalhe = getattr(resposta.stop_details, "explanation", None)
            raise ClaudeIndisponivelError(detalhe or "Pedido recusado pelo modelo.")

        texto_json = next(
            (bloco.text for bloco in resposta.content if bloco.type == "text"), None
        )
        if texto_json is None:
            raise ClaudeIndisponivelError("Resposta da Claude sem conteúdo de texto.")

        try:
            return Intencao.model_validate(json.loads(texto_json))
        except (json.JSONDecodeError, ValidationError) as exc:
            logger.warning("Resposta da Claude fora do formato esperado: %s", exc)
            raise ClaudeIndisponivelError(
                "Resposta da Claude fora do formato esperado."
            ) from exc


@lru_cache(maxsize=1)
def _claude_client() -> ClaudeClient:
    return ClaudeClient(settings)


def get_claude_client() -> ClaudeClient:
    """Dependência do FastAPI — sobrescrita via ``app.dependency_overrides``."""
    return _claude_client()
