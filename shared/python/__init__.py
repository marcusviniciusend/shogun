"""Contratos compartilhados entre o servidor Shogun e os clientes."""

from typing import Literal

from pydantic import BaseModel


class ClientInstruction(BaseModel):
    """Instrucao executavel que o servidor delega ao cliente.

    O servidor pode rodar em outra maquina e nao tem acesso ao SO do usuario;
    quem executa e o cliente. `type` discrimina a instrucao (hoje so
    `open_app`). O cliente que nao suportar o alvo — no mobile so uma lista
    curada de apps e viavel, porque deep links exigem schemes declarados de
    antemao — nao executa nada e usa `fallback_text` como resposta ao usuario.
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
