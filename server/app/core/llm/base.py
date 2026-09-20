"""Contrato comum a todos os provedores de LLM do Shogun.

A personalidade do Shogun (``SYSTEM_PROMPT``) e o formato de saída
(``ESQUEMA_COMANDO`` / ``ComandoInterpretado``) vivem aqui e são idênticos para
todos os provedores — trocar de LLM não pode mudar quem o Shogun é.

O significado de cada ação vive em ``SEMANTICA_ACOES``, fonte única da qual o
``ESQUEMA_COMANDO`` e a ``DICA_ESQUEMA`` são derivados: os dois canais existem
porque nem todo provedor recebe o schema, não porque a semântica seja duas.
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

# Significado de cada ação, em linguagem natural. FONTE ÚNICA: o
# `ESQUEMA_COMANDO` (o json_schema que claude e openai_mini recebem) e a
# `DICA_ESQUEMA` (o único canal em linguagem natural de deepseek e ollama) são
# os dois DERIVADOS daqui. Não reescreva a semântica de uma ação em nenhum dos
# dois — os quatro provedores têm que receber a mesma frase, e dois textos sobre
# a mesma coisa divergem em silêncio.
#
# Os estados de agente estão escritos à mão de propósito: derivá-los de
# `StatusAgente` (`domain/pendencias.py`) tornaria `test_semantica_acoes.py`
# tautológico — é justamente daquele enum que o teste deriva o vocabulário
# esperado aqui.
SEMANTICA_ACOES: dict[str, str] = {
    # Definida por COMPLEMENTO, e não por lista de tópicos. A redação anterior
    # ("resposta livre e qualquer pergunta geral, inclusive horário, data,
    # clima, agenda pessoal") fazia dois trabalhos na mesma oração: roteava a
    # pergunta para cá E declarava que o Shogun cobre esses assuntos. O modelo
    # obedecia as duas — roteava certo e inventava o compromisso. Os tópicos
    # continuam nomeados porque é isso que move um 7B; o que saiu foi a promessa
    # implícita, e a última oração é quem corta o fio entre uma coisa e a outra.
    "conversar": (
        "destino padrão: tudo que não é status de agente de software nem abrir "
        "aplicativo cai aqui — conversa, perguntas gerais, horário, data, "
        "agenda do Marcus, clima. Cair aqui não quer dizer que o Shogun tenha o "
        "dado."
    ),
    "consultar_pendencias": (
        "status dos AGENTES de software que o Shogun acompanha (executando, "
        "pendente, travado, erro, concluido). Não é agenda, compromisso, "
        "horário nem lista de tarefas do Marcus."
    ),
    "abrir_app": "abrir um aplicativo no dispositivo.",
}

#: Uma frase por ação, na ordem de `ACOES`, no formato ``acao = significado``.
#: É a forma em que os dois canais de prompt consomem `SEMANTICA_ACOES`.
_SEMANTICA_POR_ACAO: tuple[str, ...] = tuple(
    f"{acao} = {SEMANTICA_ACOES[acao]}" for acao in ACOES
)

# Como escrever `resposta_falada`. FONTE ÚNICA, no mesmo padrão de
# `SEMANTICA_ACOES`: a `description` de `resposta_falada` no `ESQUEMA_COMANDO` e
# a `DICA_ESQUEMA` derivam daqui, e é aqui que se edita.
#
# Existe porque `conversar` é o ÚNICO ramo da rota cuja fala não passa por dado
# do servidor: `consultar_pendencias` constrói a resposta de `Pendencia` real e
# `abrir_app` constrói do parâmetro já validado — os dois DESCARTAM a
# `resposta_falada` do modelo. Em `conversar` ela é falada verbatim
# (`api/comando.py`). É por ali, e só por ali, que uma alucinação chega ao
# Marcus.
#
# A regra é geral de propósito, não sobre agenda: alcança clima, e-mail e o que
# aparecer depois, sem rodada nova. E ela só é barata porque o prompt agora
# carrega data e hora reais (`contexto.py`) — sem essa âncora, "diga só o que
# estiver neste prompt" viraria mordaça e proibiria o Shogun de responder uma
# hora que o servidor sabe.
REGRA_DE_HONESTIDADE = (
    "Diga só o que estiver neste prompt. Quando a resposta depende de dado que "
    "não está aqui — a agenda do Marcus, o clima, e-mail, arquivos — diga que "
    "não tem acesso a esse dado. Nunca invente hora, data, nome, número nem "
    "compromisso."
)

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
            # Derivada de `SEMANTICA_ACOES` — não escreva a semântica aqui.
            "description": " ".join(_SEMANTICA_POR_ACAO),
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
            # A regra vem de `REGRA_DE_HONESTIDADE` — não a escreva aqui.
            "description": (
                "Texto que será falado ao Marcus, em português do Brasil. "
                + REGRA_DE_HONESTIDADE
            ),
        },
    },
    "required": ["acao", "parametros", "resposta_falada"],
    "additionalProperties": False,
}

# Provedores sem enforcement de schema (ex.: JSON mode do DeepSeek) recebem o
# schema no próprio prompt. É um ACRÉSCIMO ao SYSTEM_PROMPT, nunca uma alteração
# dele — a personalidade continua idêntica em todos os provedores.
#
# O bloco de ações não é redundante nem para quem tem enforcement: o ollama
# recebe o `ESQUEMA_COMANDO` como gramática, e gramática garante forma, não
# semântica (`ollama.py`). A `DICA_ESQUEMA` é o único canal em linguagem natural
# de deepseek e ollama — é por aqui que o significado das ações chega neles.
DICA_ESQUEMA = (
    "\n\nResponda SEMPRE com um único objeto JSON válido, sem markdown e sem "
    "texto fora do JSON, exatamente neste formato:\n"
    '{"acao": "conversar" | "consultar_pendencias" | "abrir_app", '
    '"parametros": {"app": string | null, "limite": integer | null}, '
    '"resposta_falada": string}'
    # Derivado de `SEMANTICA_ACOES` — não escreva a semântica aqui.
    #
    # Acentuado de propósito: a medição do Kama mostrou que acento e pontuação
    # mudam a classificação nesses modelos ("que horas sao agora", sem acento,
    # não reproduz o bug que a frase acentuada reproduz 5/5). O texto em volta é
    # português acentuado; esta linha não pode ser a exceção. Fica sem acento só
    # o que é identificador — chave de JSON, valor do enum de ação, estado de
    # `StatusAgente` — porque ali a grafia literal é o que importa.
    "\n\nQuando usar cada ação:\n"
    + "\n".join(f"- {frase}" for frase in _SEMANTICA_POR_ACAO)
    # Derivado de `REGRA_DE_HONESTIDADE` — não escreva a regra aqui. Alcança
    # deepseek e ollama, os dois que não recebem o schema como texto e que
    # ficariam sem a regra se ela morasse só na `description`.
    + "\n\nAo escrever resposta_falada: "
    + REGRA_DE_HONESTIDADE
)


class UsoTokens(BaseModel):
    """Consumo real de tokens de UMA chamada ao provedor.

    Preenchido pelo próprio provedor a partir do que a API dele reporta
    (``usage`` na Anthropic/OpenAI/DeepSeek, ``prompt_eval_count`` /
    ``eval_count`` no Ollama). ``provider`` é o nome de quem de fato atendeu —
    com fallback, o reserva; nunca o nome composto do wrapper.
    """

    provider: str
    input_tokens: int = 0
    output_tokens: int = 0


class ComandoInterpretado(BaseModel):
    """Interpretação estruturada de um comando, independente do provedor."""

    acao: Acao = "conversar"
    parametros: dict[str, Any] = Field(default_factory=dict)
    resposta_falada: str
    # Telemetria, não interpretação: nunca vem do JSON do modelo (ver
    # `parsear_comando`) — quem o preenche é o código do provedor, depois do
    # parse. `None` = provedor sem medição (ex.: deterministico, que não chama
    # LLM nenhum).
    uso: UsoTokens | None = None


class LLMIndisponivelError(RuntimeError):
    """O provedor de LLM não pôde ser consultado ou devolveu algo inválido.

    Erro único e comum a todos os provedores: é o que a rota trata e o que
    dispara o fallback automático.
    """


class ConfiguracaoInvalidaError(ValueError):
    """O provedor esta mal configurado e nao pode nem ser construido.

    Diferente de :class:`LLMIndisponivelError`, que e uma falha em tempo de
    chamada e aciona o fallback: aqui nao ha o que tentar de novo nem para onde
    cair — falta uma variavel de ambiente. Por isso e levantado no construtor e
    derruba o boot, como :class:`ProviderDesconhecidoError` ja faz para um nome
    de provedor invalido.
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

    if isinstance(dados, dict):
        # `uso` é preenchido pelo código do provedor, nunca pelo modelo: um
        # LLM que alucine (ou injete) o campo não pode falsear a telemetria
        # nem derrubar a validação.
        dados.pop("uso", None)

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
