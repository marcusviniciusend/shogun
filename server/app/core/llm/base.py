"""Contrato comum a todos os provedores de LLM do Shogun.

A personalidade do Shogun (``SYSTEM_PROMPT``) e o formato de saída
(``ESQUEMA_COMANDO`` / ``ComandoInterpretado``) vivem aqui e são idênticos para
todos os provedores — trocar de LLM não pode mudar quem o Shogun é.
"""

from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field

SYSTEM_PROMPT = (
    "Você é o Shogun, assistente pessoal de confiança do Marcus. Responda de forma "
    "direta e respeitosa, como um conselheiro. Interprete comandos e responda em "
    "JSON estruturado com: { acao: string, parametros: object, resposta_falada: string }"
)

Acao = Literal["conversar", "consultar_pendencias", "abrir_app"]

ACOES: tuple[str, ...] = ("conversar", "consultar_pendencias", "abrir_app")

# O schema enviado na requisição é FECHADO (`additionalProperties: false` em todo
# objeto): tanto o structured output da Anthropic quanto o strict mode da OpenAI
# rejeitam objetos abertos. Por isso `parametros` declara explicitamente os campos
# conhecidos como anuláveis, em vez de ser um objeto livre. Os nulos são
# descartados na desserialização, então `ComandoInterpretado.parametros` continua
# sendo um dict comum. Ao criar uma ação nova com parâmetro novo, some o campo aqui.
ESQUEMA_COMANDO: dict[str, Any] = {
    "type": "object",
    "properties": {
        "acao": {
            "type": "string",
            "enum": list(ACOES),
            "description": (
                "conversar = resposta livre; consultar_pendencias = o Marcus quer "
                "saber o que está pendente; abrir_app = abrir um aplicativo no "
                "dispositivo."
            ),
        },
        "parametros": {
            "type": "object",
            "description": "Parâmetros da ação. Use null nos campos que não se aplicam.",
            "properties": {
                "app": {
                    "anyOf": [{"type": "string"}, {"type": "null"}],
                    "description": "Nome do aplicativo a abrir (só para abrir_app).",
                },
                "limite": {
                    "anyOf": [{"type": "integer"}, {"type": "null"}],
                    "description": (
                        "Quantidade máxima de pendências a listar "
                        "(só para consultar_pendencias)."
                    ),
                },
            },
            "required": ["app", "limite"],
            "additionalProperties": False,
        },
        "resposta_falada": {
            "type": "string",
            "description": "Texto que será falado ao Marcus, em português do Brasil.",
        },
    },
    "required": ["acao", "parametros", "resposta_falada"],
    "additionalProperties": False,
}

# Provedores sem enforcement de schema (ex.: JSON mode do DeepSeek) recebem o
# schema no próprio prompt. É um ACRÉSCIMO ao SYSTEM_PROMPT, nunca uma alteração
# dele — a personalidade continua idêntica em todos os provedores.
DICA_ESQUEMA = (
    "\n\nResponda SEMPRE com um único objeto JSON válido, sem markdown e sem "
    "texto fora do JSON, exatamente neste formato:\n"
    '{"acao": "conversar" | "consultar_pendencias" | "abrir_app", '
    '"parametros": {"app": string | null, "limite": integer | null}, '
    '"resposta_falada": string}'
)


class ComandoInterpretado(BaseModel):
    """Interpretação estruturada de um comando, independente do provedor."""

    acao: Acao = "conversar"
    parametros: dict[str, Any] = Field(default_factory=dict)
    resposta_falada: str


class LLMIndisponivelError(RuntimeError):
    """O provedor de LLM não pôde ser consultado ou devolveu algo inválido.

    Erro único e comum a todos os provedores: é o que a rota trata e o que
    dispara o fallback automático.
    """


@runtime_checkable
class LLMProvider(Protocol):
    """Interface que todo provedor de LLM do Shogun implementa."""

    #: Identificador usado no registro e nos logs (ex.: ``"claude"``).
    nome: str

    @property
    def configurado(self) -> bool:
        """``True`` quando há credencial para chamar o provedor."""
        ...

    async def interpretar_comando(self, texto: str) -> ComandoInterpretado:
        """Interpreta o comando e devolve a intenção validada.

        Levanta :class:`LLMIndisponivelError` em qualquer falha (rede, timeout,
        rate limit, erro de API, resposta fora do formato).
        """
        ...


def parsear_comando(texto_json: str) -> ComandoInterpretado:
    """Converte o JSON bruto do provedor em :class:`ComandoInterpretado`.

    Descarta os campos nulos de ``parametros`` — eles existem só para satisfazer
    o schema fechado exigido pelas APIs.
    """
    import json

    from pydantic import ValidationError

    try:
        dados = json.loads(texto_json)
    except json.JSONDecodeError as exc:
        raise LLMIndisponivelError(f"Resposta não é JSON válido: {exc}") from exc

    if isinstance(dados, dict) and isinstance(dados.get("parametros"), dict):
        dados["parametros"] = {
            chave: valor
            for chave, valor in dados["parametros"].items()
            if valor is not None
        }

    try:
        return ComandoInterpretado.model_validate(dados)
    except ValidationError as exc:
        raise LLMIndisponivelError(f"Resposta fora do formato esperado: {exc}") from exc
