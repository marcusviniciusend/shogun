"""Interface (temporária) do provedor de pendências.

⚠️ TEMPORÁRIO — este módulo existe para o servidor não ficar bloqueado enquanto o
módulo de domínio do ``agente-contratos`` não existe fisicamente. No merge:

* substituir ``Pendencia`` e ``PendenciasProvider`` pelos tipos oficiais do
  módulo de domínio (provavelmente em ``shared/python`` ou ``server/app/domain``);
* manter ``get_pendencias_provider`` como ponto de injeção do FastAPI, apenas
  trocando o que ele devolve.

A assinatura assumida é ``async listar_pendencias(limite: int) -> Sequence[Pendencia]``.
Se a interface definitiva divergir, o ajuste fica restrito a este arquivo e ao
adaptador em ``app/api/comando.py``.
"""

from typing import Protocol, Sequence, runtime_checkable

from pydantic import BaseModel


class Pendencia(BaseModel):
    """Um item pendente na vida do Marcus."""

    titulo: str
    detalhe: str | None = None
    prazo: str | None = None


@runtime_checkable
class PendenciasProvider(Protocol):
    """Fonte de pendências consultada pela ação ``consultar_pendencias``."""

    async def listar_pendencias(self, limite: int = 10) -> Sequence[Pendencia]: ...


class PendenciasProviderStub:
    """Implementação vazia usada até o provedor real existir.

    Não inventa dados: devolve lista vazia, e a resposta falada deixa claro que a
    fonte de pendências ainda não está conectada.
    """

    disponivel = False

    async def listar_pendencias(self, limite: int = 10) -> Sequence[Pendencia]:
        return []


_provider: PendenciasProvider = PendenciasProviderStub()


def get_pendencias_provider() -> PendenciasProvider:
    """Dependência do FastAPI — sobrescrita via ``app.dependency_overrides``."""
    return _provider
