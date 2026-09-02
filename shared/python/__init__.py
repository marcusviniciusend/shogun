"""Contratos compartilhados entre o servidor Shogun e os clientes."""

from typing import Literal

from pydantic import BaseModel


class AgentAction(BaseModel):
    agent: str
    status: Literal["ok", "error"]
    detail: str | None = None


class CommandRequest(BaseModel):
    """Mensagem enviada por um cliente ao servidor."""

    session_id: str
    text: str
    client: Literal["desktop", "mobile"]


class CommandResponse(BaseModel):
    """Resposta do servidor a um comando."""

    session_id: str
    text: str
    actions: list[AgentAction] = []
