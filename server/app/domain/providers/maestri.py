"""Provider de pendências apoiado na API do Maestri.

Placeholder: a API do Maestri ainda não foi definida, então os métodos ficam com
TODO. A assinatura já é a final — quando a API existir, basta preencher o corpo.
"""

from ..pendencias import Pendencia, PendenciasProvider, StatusAgente


class MaestriProvider(PendenciasProvider):
    """Lê as pendências dos agentes diretamente do Maestri."""

    def __init__(self, base_url: str, api_key: str | None = None, timeout: float = 5.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def get_pendencias_agentes(self) -> list[Pendencia]:
        # TODO: chamar o endpoint de pendências do Maestri (rota ainda indefinida)
        #       e mapear cada item da resposta para `Pendencia`.
        raise NotImplementedError("API do Maestri ainda não definida.")

    def get_status_agente(self, agente_id: str) -> StatusAgente:
        # TODO: chamar o endpoint de status do agente no Maestri e traduzir o
        #       vocabulário de estados dele para `StatusAgente`.
        raise NotImplementedError("API do Maestri ainda não definida.")
