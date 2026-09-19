"""Guarda da semântica das ações — o texto que ensina o LLM a classificar.

`SEMANTICA_ACOES` (`core/llm/base.py`) é a fonte única do significado de cada
valor de `Acao`. O `ESQUEMA_COMANDO` (o json_schema que claude e openai_mini
recebem) e a `DICA_ESQUEMA` (o único canal em linguagem natural de deepseek e
ollama) são derivados dela.

Esse texto é a única coisa que separa "pendência = status de agente" de
"pendência = o que o Marcus tem para fazer". Quando ele era genérico, modelos
pequenos classificavam pergunta de horário como `consultar_pendencias` — 3/3
com `qwen2.5:7b` e com `hermes3:8b`. É prompt que muda comportamento e que
nenhum tipo representa: exatamente o perfil de coisa que apodrece em silêncio.

## O que cada teste ancora, e por quê assim

Mesma linha de `test_invariantes_contrato.py`: **nada aqui compara redação.**

- **Cobertura** (`test_toda_acao_tem_semantica`) — igualdade de conjuntos
  contra `ACOES`, nos dois sentidos. Ação nova sem descrição falha; descrição
  órfã de ação removida também. Sem isso, o "some o campo aqui" do comentário
  do `ESQUEMA_COMANDO` continua sendo só um pedido educado.
- **Vocabulário do domínio** (`test_semantica_de_pendencias_cita_o_vocabulario_do_dominio`)
  — os termos são **derivados de `StatusAgente`** (`domain/pendencias.py`), não
  escritos à mão aqui. Reescrever a prosa inteira passa; perder a ligação com o
  domínio não.

## O que estes testes NÃO pegam — de propósito

Nenhum deles verifica que a descrição **funciona**. Isso só se mede chamando
modelo de verdade, e o CI não tem rede nem segredo. A garantia é mais modesta e
é a que faltava: o vocabulário do domínio não **desaparece** da descrição, e os
dois canais de prompt não divergem — eles não podem, saem da mesma constante.

Também não existe (e não deve existir) uma lista negativa do tipo "a descrição
não pode conter `horario`/`agenda`". A redação atual contém essas palavras de
propósito, nas duas pontas: reivindicadas em `conversar`, excluídas em
`consultar_pendencias`. Uma guarda negativa proibiria justamente a correção.
"""

import re

from app.core.llm import ACOES, DICA_ESQUEMA, ESQUEMA_COMANDO, SEMANTICA_ACOES
from app.domain.pendencias import StatusAgente

#: `pendente` fica **fora** do vocabulário que ancora a descrição.
#:
#: `StatusAgente.PENDENTE` vale `"pendente"`, que é exatamente a palavra
#: genérica de que o bug era feito: a descrição antiga ("o Marcus quer saber o
#: que está pendente") passaria neste teste sem nenhuma correção. Mesma razão
#: que deixou `"mobile"`/`"desktop"` fora de `_termos_do_contrato()` em
#: `test_invariantes_contrato.py` — palavra que é prosa portuguesa tanto quanto
#: identificador não ancora nada.
_ESTADOS_QUE_ANCORAM = {s.value for s in StatusAgente} - {StatusAgente.PENDENTE.value}


def _menciona(texto: str, termo: str) -> bool:
    """`termo` como palavra inteira, ignorando caixa."""
    return re.search(rf"\b{re.escape(termo)}\b", texto, re.IGNORECASE) is not None


def test_toda_acao_tem_semantica():
    """`SEMANTICA_ACOES` e `ACOES` andam juntas, nos dois sentidos.

    Ação nova sem descrição entraria no enum com significado nenhum para o
    modelo — o bug desta rodada, de novo e por omissão. Descrição órfã de ação
    removida é prompt mentindo sobre um valor que não existe mais.
    """
    assert set(SEMANTICA_ACOES) == set(ACOES), (
        "SEMANTICA_ACOES e ACOES divergiram — "
        f"sem descrição: {sorted(set(ACOES) - set(SEMANTICA_ACOES))}, "
        f"sem ação: {sorted(set(SEMANTICA_ACOES) - set(ACOES))}. "
        "Toda ação do enum precisa dizer ao modelo quando é usada."
    )


def test_semantica_de_pendencias_cita_o_vocabulario_do_dominio():
    """A descrição de `consultar_pendencias` tem que falar do domínio real.

    Pendência no Shogun é **status de agente** (`StatusAgente`), não agenda do
    Marcus. A âncora são os termos do domínio: `agente` e pelo menos um estado
    do enum. Reescrever a redação é livre; perder o vocabulário não.
    """
    descricao = SEMANTICA_ACOES["consultar_pendencias"]

    assert _menciona(descricao, "agente") or _menciona(descricao, "agentes"), (
        "a descrição de consultar_pendencias não cita `agente`. É a palavra que "
        "separa status de agente de agenda pessoal — sem ela, modelo pequeno "
        "volta a classificar pergunta de horário como pendência."
    )

    citados = {e for e in _ESTADOS_QUE_ANCORAM if _menciona(descricao, e)}
    assert citados, (
        "a descrição de consultar_pendencias não cita nenhum estado de "
        f"StatusAgente ({sorted(_ESTADOS_QUE_ANCORAM)}). Citar os estados é o "
        "que torna a ação concreta para o modelo. `pendente` não conta de "
        "propósito: é a palavra genérica de que o bug era feito."
    )


def test_os_dois_canais_de_prompt_carregam_a_mesma_semantica():
    """Nenhum provedor fica sem o significado das ações.

    `claude` e `openai_mini` recebem a semântica pela `description` do
    `ESQUEMA_COMANDO`; `deepseek` e `ollama` só a recebem pela `DICA_ESQUEMA` —
    o primeiro não recebe schema nenhum, o segundo recebe o schema como
    gramática, que garante forma e não semântica. Um canal que deixe de derivar
    de `SEMANTICA_ACOES` cega metade dos provedores em silêncio.
    """
    descricao_do_enum = ESQUEMA_COMANDO["properties"]["acao"]["description"]
    for acao, significado in SEMANTICA_ACOES.items():
        assert significado in descricao_do_enum, (
            f"a semântica de {acao} não está na description do ESQUEMA_COMANDO "
            "— claude e openai_mini deixariam de recebê-la. A description é "
            "derivada de SEMANTICA_ACOES; não a escreva à mão."
        )
        assert significado in DICA_ESQUEMA, (
            f"a semântica de {acao} não está na DICA_ESQUEMA — deepseek e "
            "ollama deixariam de recebê-la, e é justamente onde o bug de "
            "classificação foi reproduzido. A dica é derivada de "
            "SEMANTICA_ACOES; não a escreva à mão."
        )
