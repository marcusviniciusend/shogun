"""Data e hora reais para o prompt — o Shogun para de chutar a hora.

O servidor tem relógio e, até aqui, não o entregava ao modelo: nada em
`core/llm/` importava `datetime`, e o único uso no projeto era `agora_utc()` em
`db/models.py`, para persistência. Perguntado que horas são, o modelo respondia
um horário inventado.

Isto não vive no `SYSTEM_PROMPT` de propósito. O instante muda a cada chamada e
o system é o **prefixo estável** do prompt (`docs/roteamento-por-complexidade.md`
mapeia esse prefixo): carimbar relógio ali envenenaria a única parte cacheável.
O bloco entra por `montar_prompt`, junto do histórico, que já é montado por
chamada.

Também não entra no histórico **persistido**: `montar_prompt` monta na hora da
chamada, e a mensagem salva continua sendo o texto cru. Carimbar a hora dentro
da mensagem gravada faria toda conversa antiga carregar horas velhas como se
fossem contexto.

**Premissa de fuso:** o instante é a hora **local do servidor**
(`datetime.now().astimezone()` no chamador). Hoje o servidor roda na máquina do
Marcus, então local é o certo e não há configuração para isso — seria opção sem
usuário. No dia em que o servidor sair da máquina dele, é esta premissa que
precisa mudar.
"""

from datetime import datetime

# Nomes escritos à mão, não vindos de `locale`: o nome do mês e do dia depende
# de locale instalado no sistema operacional, que varia entre a máquina do
# Marcus e o CI e não é garantido em imagem nenhuma. Uma tupla é determinística
# e o prompt precisa ser sempre o mesmo texto.
DIAS_DA_SEMANA = (
    "segunda-feira",
    "terça-feira",
    "quarta-feira",
    "quinta-feira",
    "sexta-feira",
    "sábado",
    "domingo",
)

MESES = (
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
)


def bloco_de_contexto(agora: datetime) -> str:
    """Dia da semana, data e hora de ``agora``, prontos para entrar no prompt.

    Função pura: recebe o instante, não o lê. Quem lê o relógio é a rota, e é
    por isso que este módulo é testável sem congelar tempo.

    O **dia da semana** não é enfeite. "amanhã" e "hoje à tarde" são as frases
    que motivaram esta função, e sem o dia da semana o modelo não consegue nem
    resolver o que "amanhã" quer dizer. Quem achar o bloco verboso vai querer
    cortá-lo primeiro — não corte.
    """
    dia_da_semana = DIAS_DA_SEMANA[agora.weekday()]
    mes = MESES[agora.month - 1]
    return (
        f"Data e hora de agora: {dia_da_semana}, {agora.day} de {mes} de "
        f"{agora.year}, {agora:%H:%M} (hora local do servidor). "
        "Use isto para responder qualquer pergunta sobre hora ou data."
    )
