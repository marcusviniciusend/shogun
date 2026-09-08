"""Rate limit por token autenticado — protecao de custo, nao de seguranca.

Motivo: o servidor fica exposto via Tailscale e o POST /comando aciona LLM
pago; um cliente com bug em loop (ou o proprio retry automatico do desktop)
martelaria o modelo e geraria custo real. O limite e por token apresentado,
com janela deslizante de 60s.

Dois baldes, porque as rotas tem custo muito diferente:

- **comando** (``SHOGUN_RATE_LIMIT_COMANDO_POR_MINUTO``, default 20/min):
  cada chamada paga LLM. 20/min e mais do que qualquer uso por voz real e
  ainda corta um loop desgovernado em segundos.
- **leitura** (``SHOGUN_RATE_LIMIT_LEITURA_POR_MINUTO``, default 120/min):
  /pendencias, /sessoes e /consumo so leem o banco local. O painel do desktop
  faz polling de 30s (2/min por endpoint) — 120/min nao chega perto de
  atrapalhar o uso normal e ainda limita abuso. Zero em qualquer um desliga o
  balde.

Estoura = 429 com header ``Retry-After`` (segundos, inteiro, arredondado para
cima) e mensagem dizendo o limite.

LIMITACAO DOCUMENTADA: o contador vive em memoria do processo — zera no
restart e nao e compartilhado entre instancias. Para o Shogun, servidor de
instancia unica e usuario unico, e o suficiente; multiplas instancias
exigiriam um armazenamento compartilhado (ex.: Redis), complexidade que hoje
nao se justifica. Sem token configurado (dev local), todas as chamadas caem
num balde unico.
"""

import math
import time
from collections import deque
from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings
from app.core.security import get_settings

_bearer = HTTPBearer(auto_error=False)

#: Chave do balde quando a autenticacao esta desligada (dev local).
_CHAVE_ANONIMA = "anon"

_JANELA_SEGUNDOS = 60.0


class JanelaDeslizante:
    """Janela deslizante de 60s por chave, em memoria.

    ``relogio`` e injetavel para os testes controlarem o tempo; o default e
    ``time.monotonic``, imune a ajuste de relogio do sistema.
    """

    def __init__(self, relogio: Callable[[], float] = time.monotonic) -> None:
        self._relogio = relogio
        self._chamadas: dict[str, deque[float]] = {}

    def registrar(self, chave: str, limite: int) -> float | None:
        """Registra uma chamada. ``None`` = dentro do limite; senao, devolve
        quantos segundos faltam para a chamada mais antiga sair da janela."""
        agora = self._relogio()
        fila = self._chamadas.setdefault(chave, deque())
        while fila and agora - fila[0] >= _JANELA_SEGUNDOS:
            fila.popleft()

        if len(fila) >= limite:
            return _JANELA_SEGUNDOS - (agora - fila[0])

        fila.append(agora)
        return None

    def limpar(self) -> None:
        """Zera todos os baldes — usado pelos testes."""
        self._chamadas.clear()


_janela_comando = JanelaDeslizante()
_janela_leitura = JanelaDeslizante()


def redefinir() -> None:
    """Zera o estado global do rate limit (fixture de teste)."""
    _janela_comando.limpar()
    _janela_leitura.limpar()


def _chave(credentials: HTTPAuthorizationCredentials | None) -> str:
    return credentials.credentials if credentials is not None else _CHAVE_ANONIMA


def _verificar(
    janela: JanelaDeslizante,
    chave: str,
    limite: int,
    rota: str,
) -> None:
    if limite <= 0:  # zero/negativo = balde desligado
        return
    espera = janela.registrar(chave, limite)
    if espera is None:
        return
    segundos = max(1, math.ceil(espera))
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=(
            f"Limite de {limite} chamadas por minuto em {rota} atingido. "
            f"Tente de novo em {segundos}s."
        ),
        headers={"Retry-After": str(segundos)},
    )


async def limitar_comando(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    config: Settings = Depends(get_settings),
) -> None:
    """Balde do POST /comando. Declarar DEPOIS de ``require_auth`` no router:
    token invalido tem que virar 401 sem consumir cota de ninguem."""
    _verificar(
        _janela_comando,
        _chave(credentials),
        config.shogun_rate_limit_comando_por_minuto,
        "/comando",
    )


async def limitar_leitura(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    config: Settings = Depends(get_settings),
) -> None:
    """Balde compartilhado das rotas de leitura (/pendencias, /sessoes,
    /consumo) — frouxo o bastante para o polling do painel nunca esbarrar."""
    _verificar(
        _janela_leitura,
        _chave(credentials),
        config.shogun_rate_limit_leitura_por_minuto,
        "rotas de leitura",
    )
