"""Guarda do bloco de data e hora que a rota antepõe a todo comando.

`bloco_de_contexto` (`core/llm/contexto.py`) é o que impede o Shogun de chutar a
hora. Antes dele o servidor tinha relógio e não o entregava ao modelo, e
"14:30" às 19:47 era o resultado.

O teste compara **campos derivados do próprio `datetime`** — dia, mês, hora —
e não a string inteira. Comparar a string faria o teste virar cópia da
implementação: qualquer ajuste de redação ficaria caro sem ganho nenhum, e a
redação deste bloco é justamente o que vai ser afinado quando a medição com
modelo real pedir.
"""

from datetime import datetime

from app.core.llm.contexto import DIAS_DA_SEMANA, MESES, bloco_de_contexto

#: Uma sexta-feira, à tarde, com dia e mês de dois dígitos — nada de valores que
#: passariam por acidente (dia 1, hora 0, janeiro).
INSTANTE = datetime(2026, 9, 18, 14, 30)


def test_bloco_cita_a_data_e_a_hora_do_instante_recebido():
    """Os campos do bloco saem do `datetime`, não de um relógio interno.

    A função é pura de propósito: quem lê o relógio é a rota. É isso que torna
    este teste possível sem congelar tempo.
    """
    bloco = bloco_de_contexto(INSTANTE)

    assert str(INSTANTE.day) in bloco
    assert MESES[INSTANTE.month - 1] in bloco
    assert str(INSTANTE.year) in bloco
    assert f"{INSTANTE:%H:%M}" in bloco


def test_bloco_cita_o_dia_da_semana():
    """O dia da semana não é enfeite — é o que sustenta "amanhã".

    "Tenho algum compromisso amanhã?" e "hoje à tarde" são as frases que
    motivaram o bloco. Sem o dia da semana o modelo não consegue nem resolver o
    que "amanhã" quer dizer, e é justamente a linha que alguém cortaria por
    achar o bloco verboso.
    """
    bloco = bloco_de_contexto(INSTANTE)

    assert DIAS_DA_SEMANA[INSTANTE.weekday()] in bloco, (
        "o bloco de contexto parou de citar o dia da semana. Data e hora sem o "
        "dia da semana não respondem 'amanhã', que é a pergunta que motivou "
        "este bloco."
    )


def test_todo_dia_da_semana_e_todo_mes_tem_nome():
    """As tabelas são escritas à mão; um furo nelas é `IndexError` em produção.

    Não vêm de `locale` porque locale depende do sistema operacional e varia
    entre a máquina do Marcus e o CI. O preço disso é que a completude passa a
    ser responsabilidade nossa — daí o teste.
    """
    assert len(DIAS_DA_SEMANA) == 7
    assert len(MESES) == 12
    assert all(DIAS_DA_SEMANA) and all(MESES)


def test_o_bloco_funciona_em_qualquer_dia_do_ano():
    """Varre o ano inteiro: nenhum mês ou dia da semana estoura nem fica vazio.

    Barato e fecha a distância entre "as tabelas têm o tamanho certo" e "todo
    instante possível produz bloco", que é o que a rota precisa — ela chama esta
    função em **todo** comando, o ano inteiro.
    """
    primeiro_dia = datetime(2026, 1, 1).toordinal()

    for offset in range(365):
        momento = datetime.fromordinal(primeiro_dia + offset).replace(
            hour=offset % 24, minute=offset % 60
        )
        bloco = bloco_de_contexto(momento)

        assert DIAS_DA_SEMANA[momento.weekday()] in bloco
        assert MESES[momento.month - 1] in bloco
        assert f"{momento:%H:%M}" in bloco
