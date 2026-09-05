"""Fallback automático entre provedores de LLM."""

import logging

from app.core.llm.base import ComandoInterpretado, LLMIndisponivelError, LLMProvider

logger = logging.getLogger(__name__)


class FallbackLLMProvider:
    """Envolve dois provedores: se o principal falhar, tenta o reserva.

    Só entra em ação quando o principal levanta :class:`LLMIndisponivelError` —
    o erro comum a todas as falhas de provedor (timeout, rate limit, erro de API,
    credencial ausente, resposta fora do formato). Se o reserva também falhar, o
    erro propagado cita os dois motivos e mantém o original encadeado.
    """

    def __init__(self, principal: LLMProvider, reserva: LLMProvider) -> None:
        self.principal = principal
        self.reserva = reserva
        self.nome = f"{principal.nome}+{reserva.nome}"

    @property
    def configurado(self) -> bool:
        return self.principal.configurado or self.reserva.configurado

    async def interpretar_comando(self, texto: str) -> ComandoInterpretado:
        try:
            return await self.principal.interpretar_comando(texto)
        except LLMIndisponivelError as erro_principal:
            logger.warning(
                "Provedor '%s' falhou (%s); tentando fallback '%s'.",
                self.principal.nome,
                erro_principal,
                self.reserva.nome,
            )
            try:
                comando = await self.reserva.interpretar_comando(texto)
            except LLMIndisponivelError as erro_reserva:
                logger.error(
                    "Fallback '%s' também falhou: %s", self.reserva.nome, erro_reserva
                )
                raise LLMIndisponivelError(
                    f"{self.principal.nome}: {erro_principal} | "
                    f"{self.reserva.nome}: {erro_reserva}"
                ) from erro_principal
            logger.info("Comando atendido pelo fallback '%s'.", self.reserva.nome)
            return comando
