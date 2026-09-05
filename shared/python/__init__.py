"""Contratos compartilhados entre o servidor Shogun e os clientes."""

from typing import Literal

from pydantic import BaseModel


class AgentAction(BaseModel):
    agent: str
    status: Literal["ok", "error"]
    detail: str | None = None


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
