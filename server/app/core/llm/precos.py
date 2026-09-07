"""Tabela de preços por provedor de LLM — USD por 1 milhão de tokens.

Hardcoded de propósito: preço de API muda por decisão comercial do provedor,
não por release do Shogun, e uma constante versionada deixa a mudança visível
no diff e no `git blame`. Como atualizar (documentado também em
`docs/DATABASE.md`, seção "Rastreamento de consumo"):

1. conferir a página de preços do provedor;
2. editar o valor aqui, atualizando a data e a fonte no comentário da linha;
3. rodar a suíte — os testes de cálculo usam esta tabela.

Os preços valem para o MODELO que cada provedor usa hoje (ver os defaults em
`core/config.py`). Trocar de modelo num provedor implica revisar a linha dele.
A tabela NÃO é histórica: o custo é sempre calculado com o preço vigente,
inclusive para mensagens antigas — precisão retroativa exigiria versionar
preço por período, complexidade que não se justifica para um usuário.

Referências (capturadas em 2026-09-07):
- claude: Claude Sonnet (anthropic.com/pricing) — US$ 3,00 input / US$ 15,00
  output. ATENÇÃO: `shogun_model` hoje aponta para `claude-opus-5`
  (US$ 5,00 / US$ 25,00); a linha segue a instrução de precificar o Sonnet.
- deepseek: deepseek-chat (api-docs.deepseek.com/quick_start/pricing), tabela
  vigente desde 2025-09 — US$ 0,28 input (cache miss) / US$ 0,42 output.
- openai_mini: gpt-4o-mini (openai.com/api/pricing) — US$ 0,15 / US$ 0,60.
- ollama: modelo local, custo de API sempre zero.
"""

from pydantic import BaseModel

TOKENS_POR_MILHAO = 1_000_000


class PrecoProvider(BaseModel):
    """USD por 1M de tokens de input e de output."""

    input_usd_por_milhao: float
    output_usd_por_milhao: float


PRECOS: dict[str, PrecoProvider] = {
    "claude": PrecoProvider(input_usd_por_milhao=3.00, output_usd_por_milhao=15.00),
    "deepseek": PrecoProvider(input_usd_por_milhao=0.28, output_usd_por_milhao=0.42),
    "openai_mini": PrecoProvider(
        input_usd_por_milhao=0.15, output_usd_por_milhao=0.60
    ),
    "ollama": PrecoProvider(input_usd_por_milhao=0.0, output_usd_por_milhao=0.0),
}

# Provedor fora da tabela (ex.: `deterministico`, fakes de teste) custa zero:
# ou não chama API nenhuma, ou é um provedor novo que ainda não teve o preço
# cadastrado — e cobrança fictícia é pior que subestimar até o cadastro.
_PRECO_ZERO = PrecoProvider(input_usd_por_milhao=0.0, output_usd_por_milhao=0.0)


def custo_usd(provider: str, input_tokens: int, output_tokens: int) -> float:
    """Custo em USD de um volume de tokens no preço vigente do provedor."""
    preco = PRECOS.get(provider, _PRECO_ZERO)
    return (
        input_tokens * preco.input_usd_por_milhao
        + output_tokens * preco.output_usd_por_milhao
    ) / TOKENS_POR_MILHAO
