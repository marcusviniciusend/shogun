"""Montagem do prompt com o histórico da conversa (passo 4 do `DESIGN.md`).

Versão concatenada: o histórico entra como bloco de texto antes do comando
novo, e `interpretar_comando(texto)` continua recebendo uma string. É
deliberadamente a opção que **não** mexe na interface — trocar a assinatura
atingiria os quatro provedores de uma vez, e ainda não se sabe se a
concatenação é boa o bastante para justificar isso.

`docs/DESIGN.md` registra a alternativa: assinatura estruturada, com lista de
mensagens, se a qualidade não se sustentar.
"""

from collections.abc import Sequence

# Como cada papel aparece no bloco de histórico. Nomes, e não "user"/
# "assistant": o SYSTEM_PROMPT já apresenta o Shogun como quem fala com o
# Marcus, e manter o mesmo vocabulário evita ensinar dois jargões ao modelo.
ROTULOS = {"user": "Marcus", "assistant": "Shogun"}

CABECALHO = "Histórico da conversa (mais antigo primeiro):"
RODAPE = "Comando atual:"


def montar_prompt(
    historico: Sequence[tuple[str, str]],
    texto: str,
    contexto: str = "",
) -> str:
    """Texto único com o contexto e o histórico antes do comando novo.

    Sem histórico **e** sem contexto, devolve o comando intacto — uma conversa
    nova não deve carregar bloco vazio, que só gastaria tokens e confundiria o
    modelo com uma seção em branco.

    ``contexto`` é texto pronto, montado por quem sabe o que é contexto (hoje,
    `bloco_de_contexto` com data e hora). Este módulo não o produz nem o
    interpreta: um `historico.py` que injetasse relógio em silêncio seria uma
    surpresa para o próximo leitor. Ele entra **acima** do histórico porque vale
    para a conversa inteira, não para um turno.

    O default vazio não é comodidade de assinatura: é o que mantém o
    comportamento antigo byte a byte para quem não passa contexto.
    """
    partes: list[str] = []

    if contexto:
        partes.append(contexto)

    if historico:
        linhas = [
            f"{ROTULOS.get(role, role)}: {conteudo}" for role, conteudo in historico
        ]
        partes.append(f"{CABECALHO}\n" + "\n".join(linhas))

    if not partes:
        return texto

    return "\n\n".join(partes) + f"\n\n{RODAPE}\n{texto}"
