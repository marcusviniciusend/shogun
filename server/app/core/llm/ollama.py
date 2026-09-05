"""Provedor Ollama — modelo local, sem custo de API.

O modelo nao esta fixado aqui nem tem default: vem inteiro de ``OLLAMA_MODEL``, e
sua ausencia e um erro de configuracao levantado na construcao do provedor.

Usa o endpoint nativo ``/api/chat``, e nao o ``/v1/chat/completions`` compativel
com OpenAI que o Ollama tambem expoe. O motivo e a saida estruturada: no endpoint
nativo o campo ``format`` aceita um JSON Schema completo e o Ollama o converte em
gramatica, restringindo a decodificacao. O `"format": "json"` (JSON mode) so
garante que a saida e JSON valido, sem impor o schema — com um modelo 8B, essa
diferenca e o que separa uma resposta aproveitavel de uma que so o Pydantic
descobre estar errada.
"""

from typing import Any

import httpx

from app.core.config import Settings
from app.core.llm.base import (
    DICA_ESQUEMA,
    ESQUEMA_COMANDO,
    SYSTEM_PROMPT,
    ComandoInterpretado,
    ConfiguracaoInvalidaError,
    LLMIndisponivelError,
    parsear_comando,
)


class OllamaProvider:
    """Interpreta comandos com um modelo local servido pelo Ollama."""

    nome = "ollama"

    def __init__(
        self,
        config: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        modelo = (config.ollama_model or "").strip()
        if not modelo:
            # Erro de configuracao, nao de disponibilidade: nao ha o que tentar
            # de novo, entao falha aqui, na construcao, e nao no primeiro comando.
            raise ConfiguracaoInvalidaError(
                "OLLAMA_MODEL nao esta definida. O provedor 'ollama' nao tem "
                "modelo padrao — escolha um e informe no .env (ex.: "
                "OLLAMA_MODEL=qwen2.5:7b-instruct). A lista de candidatos, com "
                "VRAM e aderencia ao ESQUEMA_COMANDO, esta em server/README.md, "
                "secao 'Modelos candidatos'."
            )
        self._config = config
        self._modelo = modelo
        self._url = f"{config.ollama_base_url.rstrip('/')}/api/chat"
        # `transport` existe para os testes injetarem um httpx.MockTransport e
        # exercitarem o httpx de verdade (status, raise_for_status, ConnectError)
        # em vez de um cliente falso. None = comportamento normal, e o registro
        # continua podendo instanciar o provedor so com Settings.
        self._transport = transport

    @property
    def configurado(self) -> bool:
        """Sempre ``True``: modelo local nao usa credencial.

        Nao significa "o Ollama esta no ar" — isso so se descobre chamando, e a
        checagem e sincrona. Se o servico estiver fora, a falha aparece em
        ``interpretar_comando`` como :class:`LLMIndisponivelError` e o fallback
        assume.
        """
        return True

    def _system_prompt(self) -> str:
        """Personalidade identica a dos outros provedores, mais a dica de formato.

        A gramatica do Ollama ja garante a forma da saida, entao a dica e
        redundante do ponto de vista sintatico. Ela fica porque descrever os
        campos em linguagem natural ajuda um modelo 8B a escolher a acao certa —
        gramatica garante formato, nao semantica.
        """
        return SYSTEM_PROMPT + DICA_ESQUEMA

    def _payload(self, texto: str) -> dict[str, Any]:
        return {
            "model": self._modelo,
            "messages": [
                {"role": "system", "content": self._system_prompt()},
                {"role": "user", "content": texto},
            ],
            # Sem streaming: a rota quer a resposta inteira de uma vez.
            "stream": False,
            # Schema completo (nao "json"): decodificacao restrita pela gramatica.
            "format": ESQUEMA_COMANDO,
            "options": {
                "num_predict": self._config.shogun_max_tokens,
                # Interpretar comando e extracao, nao redacao criativa: com 0 o
                # mesmo comando cai sempre na mesma acao.
                "temperature": 0,
            },
        }

    async def interpretar_comando(self, texto: str) -> ComandoInterpretado:
        try:
            async with httpx.AsyncClient(
                timeout=self._config.shogun_llm_timeout,
                transport=self._transport,
            ) as client:
                resposta = await client.post(self._url, json=self._payload(texto))
                resposta.raise_for_status()
                dados = resposta.json()
        except httpx.ConnectError as exc:
            # Caso mais comum em dev: o Ollama simplesmente nao esta rodando.
            raise LLMIndisponivelError(
                f"Ollama nao respondeu em {self._url} (o servico esta rodando?): {exc}"
            ) from exc
        except httpx.TimeoutException as exc:
            raise LLMIndisponivelError(
                f"Ollama excedeu {self._config.shogun_llm_timeout}s — modelo local "
                f"pode estar carregando ou rodando em CPU: {exc}"
            ) from exc
        except httpx.HTTPStatusError as exc:
            # 404 aqui costuma ser modelo nao baixado (`ollama pull`).
            raise LLMIndisponivelError(
                f"Ollama devolveu HTTP {exc.response.status_code} para o modelo "
                f"'{self._modelo}': {exc.response.text[:200]}"
            ) from exc
        except httpx.HTTPError as exc:  # rede em geral
            raise LLMIndisponivelError(f"ollama: {exc}") from exc
        except ValueError as exc:  # corpo nao era JSON
            raise LLMIndisponivelError(
                f"Ollama devolveu resposta nao-JSON: {exc}"
            ) from exc

        if dados.get("done_reason") == "length":
            raise LLMIndisponivelError(
                "Resposta truncada por num_predict — aumente SHOGUN_MAX_TOKENS."
            )

        conteudo = (dados.get("message") or {}).get("content")
        if not conteudo:
            raise LLMIndisponivelError("ollama: resposta sem conteudo.")

        return parsear_comando(conteudo)
