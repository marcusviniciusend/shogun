"""Provedor deterministico — interpretacao por palavras-chave, sem LLM.

Nao chama rede nenhuma e nao usa credencial: a intencao e decidida por regras
fixas sobre o texto normalizado (minusculas, sem acentos). O mesmo comando cai
sempre na mesma acao, o que destrava o fluxo ponta a ponta (cliente → rota →
provedores de pendencias → resposta falada) sem depender de LLM externo.

Tambem serve de fallback final: como nunca levanta
:class:`LLMIndisponivelError`, coloca-lo em ``SHOGUN_LLM_FALLBACK_PROVIDER``
garante que o Shogun sempre responde alguma coisa, mesmo com toda a nuvem fora.
"""

import re
import unicodedata
from typing import Any

from app.core.config import Settings
from app.core.llm.base import ComandoInterpretado

#: Palavras que indicam que o Marcus quer saber o que esta pendente.
_CHAVES_PENDENCIAS = (
    "pendencia",
    "pendente",
    "tarefa",
    "afazer",
    "o que falta",
    "to-do",
    "todo list",
)

#: Verbo de abertura de app seguido do nome: "abre o spotify", "abrir spotify".
_PADRAO_ABRIR = re.compile(
    r"\b(?:abra|abre|abrir|inicie|iniciar)\s+(?:o|a|os|as)?\s*(?P<app>.+)$"
)


def _normalizar(texto: str) -> str:
    """Minusculas e sem acentos, para casar palavra-chave sem variacao grafica."""
    decomposto = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in decomposto if not unicodedata.combining(c)).strip()


class DeterministicoProvider:
    """Interpreta comandos por palavras-chave, sem chamar LLM nenhum."""

    nome = "deterministico"

    def __init__(self, config: Settings) -> None:
        # Settings e recebido so para honrar o contrato uniforme do registro;
        # nenhuma configuracao e necessaria.
        self._config = config

    @property
    def configurado(self) -> bool:
        """Sempre ``True``: regras locais nao usam credencial nem rede."""
        return True

    async def interpretar_comando(self, texto: str) -> ComandoInterpretado:
        normalizado = _normalizar(texto)

        if any(chave in normalizado for chave in _CHAVES_PENDENCIAS):
            return self._consultar_pendencias(normalizado)

        abrir = _PADRAO_ABRIR.search(normalizado)
        if abrir:
            app = abrir.group("app").strip(" .!?")
            if app:
                return ComandoInterpretado(
                    acao="abrir_app",
                    parametros={"app": app},
                    resposta_falada=f"Abrindo {app}, Marcus.",
                )

        return ComandoInterpretado(
            acao="conversar",
            parametros={},
            resposta_falada=(
                "Estou operando no modo deterministico, sem o modelo de "
                "linguagem. Posso consultar suas pendencias ou abrir um "
                "aplicativo, Marcus."
            ),
        )

    def _consultar_pendencias(self, normalizado: str) -> ComandoInterpretado:
        parametros: dict[str, Any] = {}
        numero = re.search(r"\b(\d+)\b", normalizado)
        if numero:
            parametros["limite"] = int(numero.group(1))
        return ComandoInterpretado(
            acao="consultar_pendencias",
            parametros=parametros,
            resposta_falada="Deixe-me ver o que esta pendente, Marcus.",
        )
