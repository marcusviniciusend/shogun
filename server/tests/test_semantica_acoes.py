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
  contra `ACOES`. Na prática o teste pega **um** dos dois sentidos: a descrição
  órfã, de ação que saiu de `ACOES`. O outro nunca chega até ele — ação nova sem
  descrição estoura `KeyError` em `_SEMANTICA_POR_ACAO`, no import de `base.py`,
  antes da coleta do pytest. A falha é barulhenta do mesmo jeito, que é o que
  importa; a igualdade de conjuntos fica porque fecha o lado que o import não
  fecha. Sem ela, o "some o campo aqui" do comentário do `ESQUEMA_COMANDO`
  continua sendo só um pedido educado.
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

from app.core.llm import (
    ACOES,
    DICA_ESQUEMA,
    ESQUEMA_COMANDO,
    REGRA_DE_HONESTIDADE,
    SEMANTICA_ACOES,
)
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

#: Formas de **admitir a falta de acesso**. Terminologia, não redação: uma
#: reescrita fiel da regra continua dizendo que não se tem o dado, de alguma
#: destas maneiras. Forma nova aqui é manutenção esperada — o que não pode é a
#: regra virar só "seja cuidadoso", que não diz ao modelo o que fazer.
_VERBOS_DE_RECUSA = ("não tem acesso", "não sei", "não consigo", "não tenho")

#: Exemplos de dado que o servidor **não** tem. A regra precisa nomear pelo
#: menos um: sem exemplo concreto, "dado que não está aqui" é abstrato demais
#: para um 7B ligar à pergunta que ele acabou de receber.
_DADOS_SEM_FONTE = ("agenda", "clima", "e-mail", "arquivos")


def _menciona(texto: str, termo: str) -> bool:
    """`termo` como palavra inteira, ignorando caixa."""
    return re.search(rf"\b{re.escape(termo)}\b", texto, re.IGNORECASE) is not None


def test_toda_acao_tem_semantica():
    """`SEMANTICA_ACOES` e `ACOES` andam juntas.

    O que este teste de fato executa é a **descrição órfã**: ação que saiu de
    `ACOES` e deixou o texto para trás é prompt mentindo sobre um valor que não
    existe mais.

    O sentido oposto — ação nova sem descrição, que entraria no enum com
    significado nenhum para o modelo — não chega aqui: `_SEMANTICA_POR_ACAO`
    indexa `SEMANTICA_ACOES[acao]` para cada item de `ACOES`, então a falta
    estoura `KeyError` no import de `base.py`, antes da coleta do pytest. Isso é
    deliberado e não é para ser "consertado" transformando em falha de teste: a
    falha continua barulhenta e acontece mais cedo. A asserção abaixo é de
    conjunto e não de subconjunto porque é ela quem cobre o lado que o import
    não cobre.
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


# --- Regra de honestidade ----------------------------------------------------
#
# `conversar` é o único ramo da rota cuja fala não passa por dado do servidor:
# `consultar_pendencias` e `abrir_app` descartam a `resposta_falada` do modelo e
# constroem a deles. A regra é o que separa "responder" de "inventar" nesse
# ramo, e vale o mesmo teste de alcance da semântica das ações.


def test_a_regra_de_honestidade_chega_nos_dois_canais():
    """A regra alcança os quatro provedores, não só os que recebem schema.

    Mata a mutação que o padrão desta branch já tinha ensinado a temer: alguém
    reescrever a regra à mão num dos canais, ou tirá-la de um deles. `deepseek`
    e `ollama` são os que ficariam sem — e é no ollama que a fabricação foi
    medida.
    """
    descricao_da_fala = ESQUEMA_COMANDO["properties"]["resposta_falada"]["description"]

    assert REGRA_DE_HONESTIDADE in descricao_da_fala, (
        "a regra de honestidade não está na description de resposta_falada — "
        "claude e openai_mini deixariam de recebê-la. A description é derivada "
        "de REGRA_DE_HONESTIDADE; não a escreva à mão."
    )
    assert REGRA_DE_HONESTIDADE in DICA_ESQUEMA, (
        "a regra de honestidade não está na DICA_ESQUEMA — deepseek e ollama "
        "deixariam de recebê-la, e é no ollama que a fabricação foi medida."
    )


def test_a_regra_de_honestidade_diz_o_que_fazer_quando_nao_sabe():
    """Âncora de conteúdo: recusa concreta, com exemplo de dado sem fonte.

    Não é lista de palavras proibidas — a armadilha que a rodada 1 registrou
    continua valendo, e aqui ela morderia igual: a regra **precisa** citar
    agenda e clima, que uma guarda negativa proibiria.

    O que se ancora é o oposto: a regra tem que dar uma saída ao modelo ("diga
    que não tem acesso") e nomear pelo menos um dado que o servidor não tem.
    Uma regra que só diga "não invente" deixa o modelo sem alternativa, e um 7B
    sem alternativa inventa.
    """
    recusas = [t for t in _VERBOS_DE_RECUSA if t in REGRA_DE_HONESTIDADE.lower()]
    assert recusas, (
        "a regra de honestidade não diz ao modelo COMO admitir a falta de "
        f"acesso (nenhuma de {_VERBOS_DE_RECUSA}). Proibir a invenção sem dar "
        "saída não resolve: sem alternativa, o modelo inventa. Forma de recusa "
        "nova é bem-vinda — acrescente em _VERBOS_DE_RECUSA."
    )

    dados = [d for d in _DADOS_SEM_FONTE if _menciona(REGRA_DE_HONESTIDADE, d)]
    assert dados, (
        "a regra de honestidade não nomeia nenhum dado que o servidor não tem "
        f"({_DADOS_SEM_FONTE}). 'Dado que não está aqui' sozinho é abstrato "
        "demais para o modelo ligar à pergunta que acabou de receber."
    )
