"""Contrato de pendências dos agentes.

Define o vocabulário do domínio (o que é uma pendência e em que estado um agente
está) e a interface `PendenciasProvider`, que desacopla quem consome as pendências
— a camada de API — de quem sabe obtê-las (Maestri, orquestrador próprio, etc).

Este módulo não conhece HTTP nem FastAPI: é apenas domínio.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class StatusAgente(str, Enum):
    """Estado atual de um agente sob observação do Shogun."""

    EXECUTANDO = "executando"
    PENDENTE = "pendente"
    TRAVADO = "travado"
    ERRO = "erro"
    CONCLUIDO = "concluido"


class Pendencia(BaseModel):
    """Uma pendência reportada por um agente.

    Segue o estilo dos contratos de `shared/python` (Pydantic) para que a camada
    de API possa serializar o objeto direto na resposta, sem conversão manual.
    """

    agente_id: str
    agente_nome: str
    status: StatusAgente
    descricao: str
    timestamp: datetime
    prioridade: int = Field(default=0, description="Maior valor = mais urgente.")


class PendenciasProvider(ABC):
    """Fonte de pendências e de status de agentes.

    Implementações concretas decidem de onde os dados vêm; a camada de API
    depende apenas desta interface.
    """

    @abstractmethod
    def get_pendencias_agentes(self) -> list[Pendencia]:
        """Retorna todas as pendências abertas conhecidas pela fonte."""

    @abstractmethod
    def get_status_agente(self, agente_id: str) -> StatusAgente:
        """Retorna o status atual de um agente específico."""
