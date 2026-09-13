"""Contratos compartilhados entre o servidor Shogun e os clientes."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ClientInstruction(BaseModel):
    """Instrucao executavel que o servidor delega ao cliente.

    O servidor pode rodar em outra maquina e nao tem acesso ao SO do usuario;
    quem executa e o cliente. `type` discrimina a instrucao (hoje so
    `open_app`). O cliente que nao suportar o alvo — no mobile os alvos
    precisam estar declarados no build do proprio cliente, entao so uma lista
    curada e fechada de apps e viavel — nao executa nada e usa `fallback_text`
    como resposta ao usuario.

    Quantidade: no maximo UMA instrucao por resposta. O servidor emite uma so;
    se mais de uma chegar, o cliente honra a primeira e ignora as demais —
    nunca executa varias.

    Regra de consumo (relacao com `CommandResponse.text`): o cliente DECIDE
    antes de falar. Primeiro avalia se consegue executar a instrucao (alvo no
    mapa curado local, `type` conhecido, SO disposto a abrir); depois exibe e
    fala a resposta correspondente a essa decisao; so entao executa. Decisao
    viavel: fala `text`. Inviavel, falha ou `type` desconhecido: fala
    `fallback_text` EM VEZ de `text` — nunca os dois, senao o TTS anuncia
    "Pedi para abrir o X" e se contradiz em seguida.

    Quando a execucao acontece em relacao a fala e escolha do cliente: no
    desktop decidir e executar sao o mesmo passo; no mobile abrir outro app
    joga o cliente para segundo plano e interrompe a sintese de voz, entao a
    fala vem antes. Preco assumido de falar antes: uma janela estreita em que o
    alvo passou na avaliacao e a abertura falha logo depois.

    Convencao para variantes futuros: todo novo `type` tambem carrega
    `fallback_text`, para um cliente antigo sempre ter o que responder diante
    de uma instrucao que nao reconhece.

    Invariante de seguranca, nas duas pontas: o servidor nunca envia URI,
    scheme ou comando executavel — so o NOME do app; e o cliente NUNCA constroi
    URI, scheme, caminho ou comando a partir de `app` — o alvo sai sempre de
    consulta a um mapa curado e fechado do proprio cliente. E essa combinacao
    (servidor manda nome, cliente resolve por consulta) que impede o LLM de
    apontar para um alvo arbitrario.
    """

    type: Literal["open_app"]
    # Nome do aplicativo como o LLM interpretou (ex.: "Spotify"). Resolver esse
    # nome e responsabilidade de cada cliente, sempre por consulta a um mapa
    # curado — nunca montando o alvo a partir desta string.
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
    # fallback_text. Consequencia que ja tem efeito observavel: o servidor grava
    # no historico o `text` otimista mesmo quando o cliente exibiu e falou o
    # `fallback_text` — entao reabrir a conversa por GET /sessoes/{id}/mensagens
    # mostra um sucesso que nao houve, e o mesmo historico alimenta o prompt do
    # comando seguinte. Divergencia ACEITA e documentada na v1, nao bug a
    # corrigir; um eventual POST /acao-resultado e extensao futura, nao
    # pendencia deste contrato.
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
