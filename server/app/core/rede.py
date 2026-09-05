"""Descoberta do bind real do servidor no startup.

`SHOGUN_HOST` diz o que *pretendemos* escutar; quem decide de fato é o servidor
ASGI. `uvicorn --host 0.0.0.0` ignora a variável, e uma validação que só olhasse
o `.env` deixaria passar exatamente o caso perigoso.

O uvicorn não entrega essa informação à aplicação — não há hook nem campo no
`scope` do lifespan com o host. Mas o lifespan da app roda *dentro* da tarefa do
`uvicorn.lifespan.on.LifespanOn.main`, que é quem chama
`await app(scope, receive, send)`. Esse frame carrega o `Config` do uvicorn, com
o host que ele realmente recebeu — CLI, argumento de `uvicorn.run()` ou default.
É de lá que lemos.

A leitura acontece *antes* de o socket abrir: o uvicorn roda o lifespan e só
depois faz o bind (`Server.startup()` chama `lifespan.startup()` e em seguida
`loop.create_server(...)`). Ou seja, a recusa impede o bind, não o corrige
depois.
"""

import inspect
import logging
from typing import NamedTuple

logger = logging.getLogger(__name__)

# Host reportado quando o uvicorn escuta num descritor já aberto (`--fd`): o
# endereço é desconhecido para nós, e o palpite seguro é tratar como exposto.
HOST_DESCONHECIDO = "0.0.0.0"


class BindEfetivo(NamedTuple):
    """Host que o servidor vai usar, e de onde essa informação veio."""

    host: str
    origem: str

    def __str__(self) -> str:
        return f"{self.host} ({self.origem})"


def _config_do_uvicorn():
    """O `uvicorn.Config` da execução atual, se estivermos sob uvicorn.

    Procura na pilha o frame do `LifespanOn.main`. Devolve `None` fora do
    uvicorn (testes com `TestClient`, outro servidor ASGI) — aí o chamador cai
    para `SHOGUN_HOST`.
    """
    for frame_info in inspect.stack():
        alvo = frame_info.frame.f_locals.get("self")
        config = getattr(alvo, "config", None)
        # Assinatura de um uvicorn.Config: tem host, port, uds e fd juntos.
        if config is not None and all(
            hasattr(config, atributo) for atributo in ("host", "port", "uds", "fd")
        ):
            return config
    return None


def descobrir_bind(host_configurado: str) -> BindEfetivo:
    """Host que o servidor realmente vai escutar.

    Prefere o que o uvicorn recebeu; cai para `host_configurado` quando não há
    uvicorn na pilha.
    """
    config = _config_do_uvicorn()
    if config is None:
        return BindEfetivo(host_configurado, "SHOGUN_HOST")

    if config.uds:
        # Socket de arquivo: alcançável só por quem tem acesso ao filesystem
        # local. Equivale a um bind local.
        return BindEfetivo("127.0.0.1", f"uvicorn --uds {config.uds}")

    if config.fd is not None:
        # Descritor herdado de outro processo: não dá para saber onde ele já
        # está escutando. Assume exposto — errar para o lado seguro aqui custa
        # um SHOGUN_AUTH_TOKEN, e errar para o outro custa um servidor aberto.
        return BindEfetivo(HOST_DESCONHECIDO, f"uvicorn --fd {config.fd}")

    return BindEfetivo(config.host, "uvicorn --host")
