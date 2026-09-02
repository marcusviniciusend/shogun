"""Ponte para os contratos compartilhados em ``shared/python``.

O repositório ainda não é empacotado (não há ``pyproject.toml`` instalável), então
adicionamos a raiz do monorepo ao ``sys.path`` para importar ``shared.python``.
Quando houver empacotamento, basta remover este módulo e importar direto.
"""

import sys
from pathlib import Path

_RAIZ = Path(__file__).resolve().parents[3]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from shared.python import AgentAction, CommandRequest, CommandResponse  # noqa: E402

__all__ = ["AgentAction", "CommandRequest", "CommandResponse"]
