"""Contratos compartilhados entre o servidor Shogun e os clientes."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ClientInstruction(BaseModel):
    """Instrucao executavel que o servidor delega ao cliente.

    O servidor pode rodar em outra maquina e nao tem acesso ao SO do usuario;
    quem executa e o cliente. `type` discrimina a instrucao (hoje so
    `open_app`). O cliente que nao suportar o alvo — no mobile so uma lista
    curada de apps e viavel, porque deep links exigem schemes declarados de
    antemao — nao executa nada e usa `fallback_text` como resposta ao usuario.

    Regra de consumo (relacao com `CommandResponse.text`): o cliente tenta
    executar ANTES de falar. Sucesso: fala `text`. Falha ou app nao suportado:
    fala `fallback_text` EM VEZ de `text` — nunca os dois, senao o TTS anuncia
    "Pedi para abrir o X" e se contradiz em seguida.

    Convencao para variantes futuros: todo novo `type` tambem carrega
    `fallback_text`, para um cliente antigo sempre ter o que responder diante
    de uma instrucao que nao reconhece.

    Invariante de seguranca: o servidor nunca envia URI, scheme ou comando
    executavel — so o NOME do app. O mapeamento nome -> executavel/deep link e
    sempre do cliente, entao o LLM nao consegue apontar para um alvo arbitrario.
    """

    type: Literal["open_app"]
    # Nome do aplicativo como o LLM interpretou (ex.: "Spotify"). O mapeamento
    # nome -> executavel/scheme e responsabilidade de cada cliente.
    app: str
    # Fala/exibicao quando o cliente nao consegue executar (app fora da lista
    # curada, falha ao abrir). Vem pronta do servidor, para o cliente nao ter
    # que redigir resposta nenhuma.
    fallback_text: str


class AgentAction(BaseModel):
    agent: str
    status: Literal["ok", "error"]
    detail: str | None = None
    # Preenchida quando a acao pede execucao no aparelho do usuario. Clientes
    # que ainda nao executam instrucoes apenas exibem a action como metadado —
    # nunca interpretar `detail` (texto para humano) como instrucao.
    #
    # Com instruction preenchida, `status: "ok"` significa DELEGACAO FEITA, nao
    # app aberto: o historico da sessao registra ok mesmo que o cliente caia no
    # fallback_text. Divergencia aceitavel na v1; um eventual POST
    # /acao-resultado e extensao futura, nao pendencia deste contrato.
    instruction: ClientInstruction | None = None


class CommandRequest(BaseModel):
    """Mensagem enviada por um cliente ao servidor."""

    # Nulo na primeira mensagem de uma conversa: o servidor cria a sessao e
    # devolve o id em `CommandResponse.session_id`, que o cliente guarda e
    # reenvia nas proximas.
    session_id: str | None = None
    text: str
    client: Literal["desktop", "mobile"]


class CommandResponse(BaseModel):
    """Resposta do servidor a um comando."""

    # Sempre preenchido, inclusive quando o request veio sem id: e assim que o
    # cliente descobre a sessao que o servidor abriu para ele.
    session_id: str
    text: str
    actions: list[AgentAction] = []


# -- Contratos de leitura (GET /pendencias e GET /sessoes) --------------------
#
# Promovidos das rotas quando o desktop passou a consumi-los tipado. Datetimes
# trafegam como string ISO 8601: `timestamp` de pendencia vem com fuso UTC
# ("...Z"); `criada_em`/`atualizada_em` de sessao e mensagem vem sem sufixo de
# fuso (UTC implicito, o formato interno do banco).


class PendenciaOut(BaseModel):
    """Uma pendencia aberta de um agente, como o GET /pendencias devolve.

    Espelho de fio do modelo de dominio do servidor; `status` carrega os
    valores do enum StatusAgente.
    """

    agente_id: str
    agente_nome: str
    status: Literal["executando", "pendente", "travado", "erro", "concluido"]
    descricao: str
    timestamp: datetime
    # Maior valor = mais urgente.
    prioridade: int


class PendenciasResponse(BaseModel):
    """Resposta do GET /pendencias: abertas, das mais urgentes para as menos.

    Mesma ordenacao da fala do /comando (prioridade decrescente, depois
    timestamp): o painel e a voz nao podem discordar sobre o que e mais
    urgente.
    """

    total: int
    pendencias: list[PendenciaOut]


class SessaoOut(BaseModel):
    """Resumo de uma conversa, como o GET /sessoes devolve.

    `titulo` e derivado na leitura (primeiras palavras da primeira fala do
    usuario, ou "(conversa vazia)") — o cliente sempre recebe algo exibivel.
    """

    id: str
    criada_em: datetime
    atualizada_em: datetime
    titulo: str
    total_mensagens: int


class SessoesResponse(BaseModel):
    """Resposta do GET /sessoes: da mais recentemente ativa para a mais antiga."""

    total: int
    sessoes: list[SessaoOut]


class MensagemOut(BaseModel):
    """Uma fala do historico, como o GET /sessoes/{id}/mensagens devolve."""

    autor: Literal["usuario", "shogun"]
    texto: str
    criada_em: datetime


class MensagensResponse(BaseModel):
    """Resposta do GET /sessoes/{id}/mensagens, em ordem cronologica."""

    session_id: str
    mensagens: list[MensagemOut]
