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


def montar_prompt(historico: Sequence[tuple[str, str]], texto: str) -> str:
    """Texto único com o histórico como contexto e o comando novo no fim.

    Sem histórico, devolve o comando intacto — uma conversa nova não deve
    carregar bloco de contexto vazio, que só gastaria tokens e confundiria o
    modelo com uma seção em branco.
    """
    if not historico:
        return texto

    linhas = [f"{ROTULOS.get(role, role)}: {conteudo}" for role, conteudo in historico]
    return f"{CABECALHO}\n" + "\n".join(linhas) + f"\n\n{RODAPE}\n{texto}"
