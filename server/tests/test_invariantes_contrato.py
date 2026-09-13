"""Guarda das invariantes do `ClientInstruction` que só existem em docstring.

O `CLAUDE.md` (seção "Os dois `shared/` andam juntos") nomeia o buraco que este
módulo fecha:

> Um aviso específico do `ClientInstruction`: a **regra de consumo**
> (`text` × `fallback_text`, nunca os dois) e a **invariante de segurança** (o
> servidor manda só o nome do app) vivem nas docstrings dos dois arquivos, e
> **nenhum tipo as representa**. Mudar o comportamento sem mudar as docstrings
> não quebra teste de paridade nenhum — passa a mentir em silêncio.

`test_paridade_contratos.py` compara **campos e tipos**; estas duas regras não
são campo nem tipo, então passam por baixo dele. E a docstring não é
documentação decorativa: é o **único** lugar onde as regras existem para quem
for escrever um consumidor novo. O mobile provou isso na revisão de contrato —
implementar `open_app` no celular é ler estas duas docstrings e mais nada.

Mesmo truque do teste de paridade: ler `shared/ts/index.ts` como **texto**
(sem Node no CI) e comparar com a introspecção de `shared/python`.

## O que cada teste ancora, e por quê assim

Teste de docstring apodrece quando compara frase. Aqui nada compara redação:

- **Simetria de termos** (`test_as_duas_docstrings_discutem_os_mesmos_termos`)
  — o vocabulário é **derivado dos modelos**, não escrito à mão: nomes de campo
  de todo contrato de `shared/python`, mais os valores de `ClientInstruction.type`.
  Reescrever a docstring inteira passa; perder de um lado só a menção a um
  campo falha. É a camada que pega *drift* entre as duas pontas.
- **Coocorrência em parágrafo** (regra de consumo) — a regra não é uma palavra,
  é uma **relação** entre `text` e `fallback_text`. A propriedade verificável é
  que existe um parágrafo falando dos dois. Citar um aqui e o outro três
  parágrafos abaixo perdeu a relação, mesmo com as duas palavras presentes.
- **Terminologia** (invariante de segurança) — exige que algum parágrafo
  relacione `app` ao que está barrado. `URI` e `scheme` são **os nomes das
  coisas barradas**, não uma escolha de redação; uma reescrita fiel as mantém.
  Se a terminologia mudar de verdade, o certo é acrescentar o termo novo em
  `_TERMOS_DE_ALVO_EXECUTAVEL` — a mensagem de falha diz isso.

## O que este módulo NÃO pega — de propósito

Nenhum teste verifica que a regra está **certa**: trocar "nunca os dois" por
"pode falar os dois" mantém os termos, os parágrafos e a simetria, e passa.
Semântica de prosa não é verificável aqui, e fingir que é seria pior — vira
guarda que a equipe aprende a contornar. O que estes testes garantem é mais
modesto e é exatamente o que faltava: a regra não **desaparece** de um lado só,
e as duas pontas seguem discutindo os mesmos elementos do contrato.

A exclusividade em si já tem guarda executável onde ela é executada:
`executarInstrucoes` (`desktop/src/lib/instrucoes.test.ts`) devolve **uma**
string, então falar os dois textos é estruturalmente impossível no desktop.
"""

import inspect
import re
from typing import Literal, get_args, get_origin

import pytest

from app.api.comando import _APP_PROIBIDO
from app.core.llm import ComandoInterpretado

# Reuso deliberado: um parser de TS só no repositório, e a mesma descoberta
# automática de modelos. Se o `index.ts` crescer além do subconjunto suportado,
# quem cresce é o parser de lá — não um segundo parser aqui.
from .test_paridade_contratos import INDEX_TS, MODELOS_PYTHON, _parse_ts

# --- Extração das duas docstrings -------------------------------------------

#: Bloco `/** ... */` imediatamente antes de `export interface <Nome>`. O
#: `(?!\*/)` impede que a busca atravesse o fim de um comentário anterior e
#: cole dois blocos num só.
_RE_DOC_INTERFACE = (
    r"/\*\*((?:(?!\*/).)*)\*/\s*export\s+interface\s+{nome}\s*\{{"
)


def _docstring_ts(nome: str) -> str:
    """A docstring de uma interface de `shared/ts`, sem a moldura do JSDoc."""
    fonte = INDEX_TS.read_text(encoding="utf-8")
    achado = re.search(
        _RE_DOC_INTERFACE.format(nome=re.escape(nome)), fonte, re.DOTALL
    )
    assert achado is not None, (
        f"interface {nome} em {INDEX_TS.name} está sem bloco /** */ imediatamente "
        "antes dela — a docstring é o único lugar onde as regras de consumo e de "
        "segurança existem para um consumidor novo; ela não pode sair."
    )
    linhas = [re.sub(r"^\s*\*\s?", "", linha) for linha in achado.group(1).splitlines()]
    return "\n".join(linhas).strip()


def _docstring_py(nome: str) -> str:
    modelo = MODELOS_PYTHON[nome]
    assert modelo.__doc__, (
        f"{nome} em shared/python está sem docstring — ver o motivo na mensagem "
        "gêmea de _docstring_ts."
    )
    return inspect.cleandoc(modelo.__doc__)


def _paragrafos(doc: str) -> list[str]:
    """Parágrafos com o espaço em branco normalizado.

    Achatar a quebra de linha importa: a regra de consumo atravessa três linhas
    na largura de 79 colunas, e sem isso `text` e `fallback_text` cairiam em
    "linhas" diferentes do mesmo parágrafo.
    """
    return [
        re.sub(r"\s+", " ", bloco).strip()
        for bloco in re.split(r"\n\s*\n", doc)
        if bloco.strip()
    ]


def _menciona(doc: str, termo: str) -> bool:
    """`termo` como palavra inteira.

    A fronteira de palavra é o que separa `text` de `fallback_text`: `_` conta
    como caractere de palavra, então `\\btext\\b` não casa dentro de
    `fallback_text` — e é justamente essa distinção que a simetria de termos
    depende para detectar a perda da regra de consumo.
    """
    return re.search(rf"\b{re.escape(termo)}\b", doc) is not None


@pytest.fixture(scope="module")
def docs() -> tuple[str, str]:
    """As duas docstrings de `ClientInstruction`: `(ts, python)`."""
    return _docstring_ts("ClientInstruction"), _docstring_py("ClientInstruction")


# --- Vocabulário derivado dos modelos ---------------------------------------


def _termos_do_contrato() -> set[str]:
    """Identificadores do contrato que uma docstring pode citar.

    Derivado dos modelos, como `MODELOS_PYTHON` no teste de paridade: campo
    novo em qualquer contrato de `shared/python` entra no vocabulário sozinho, e
    a partir daí precisa ser discutido nas duas pontas ou em nenhuma.

    Só nomes de campo e os valores de `ClientInstruction.type`. Valores de
    outros `Literal` ficam **fora** de propósito: `"mobile"` e `"desktop"`
    (de `CommandRequest.client`) são palavras de prosa portuguesa tanto quanto
    identificadores, e prendê-las aqui faria "no mobile" → "no celular"
    derrubar o CI sem nenhuma regra ter sido perdida.
    """
    termos: set[str] = set()
    for modelo in MODELOS_PYTHON.values():
        termos |= set(modelo.model_fields)
    anotacao = MODELOS_PYTHON["ClientInstruction"].model_fields["type"].annotation
    if get_origin(anotacao) is Literal:
        termos |= {str(valor) for valor in get_args(anotacao)}
    return termos


#: Nomes das coisas que a invariante de segurança barra do fio. Terminologia,
#: não redação: uma reescrita fiel da regra continua nomeando o que não pode
#: viajar. Termo novo aqui é manutenção esperada, não contorno do teste.
_TERMOS_DE_ALVO_EXECUTAVEL = ("URI", "scheme", "deep link")


# --- Testes ------------------------------------------------------------------


def test_regra_de_consumo_continua_nas_duas_docstrings(docs):
    """Algum parágrafo tem que relacionar `text` e `fallback_text`.

    A regra é uma relação, não uma palavra: os dois campos precisam aparecer
    **no mesmo parágrafo**. Se `text` sumir da docstring, quem implementar um
    consumidor novo não tem como saber que `fallback_text` substitui a fala em
    vez de acompanhá-la — e nenhum outro teste do repositório nota.
    """
    for ponta, doc in zip(("shared/ts", "shared/python"), docs):
        assert any(
            _menciona(paragrafo, "text") and _menciona(paragrafo, "fallback_text")
            for paragrafo in _paragrafos(doc)
        ), (
            f"a docstring de ClientInstruction em {ponta} não tem nenhum parágrafo "
            "relacionando `text` e `fallback_text`. A regra de consumo (falar um EM "
            "VEZ do outro, nunca os dois) só existe aqui: reescrever a redação é "
            "livre, perder a regra não."
        )


def test_invariante_de_seguranca_continua_nas_duas_docstrings(docs):
    """Algum parágrafo tem que ligar `app` ao que está barrado do fio.

    É a promessa que sustenta a guarda `_APP_PROIBIDO` da rota: o servidor manda
    só o NOME do app, então o mapeamento nome -> executável é sempre do cliente
    e o LLM não consegue apontar para alvo arbitrário.
    """
    for ponta, doc in zip(("shared/ts", "shared/python"), docs):
        assert any(
            _menciona(paragrafo, "app")
            and any(termo in paragrafo for termo in _TERMOS_DE_ALVO_EXECUTAVEL)
            for paragrafo in _paragrafos(doc)
        ), (
            f"a docstring de ClientInstruction em {ponta} não tem nenhum parágrafo "
            f"ligando `app` a {_TERMOS_DE_ALVO_EXECUTAVEL}. A invariante de segurança "
            "(o fio carrega só o nome do app) só existe aqui. Se a terminologia "
            "mudou de verdade, acrescente o termo novo em "
            "_TERMOS_DE_ALVO_EXECUTAVEL — não apague a regra."
        )


def test_as_duas_docstrings_discutem_os_mesmos_termos(docs):
    """As duas pontas citam exatamente os mesmos identificadores do contrato.

    A camada que pega *drift*: uma ponta que perde (ou ganha) a menção a um
    campo divergiu da outra, e a docstring do lado empobrecido passa a descrever
    um contrato que não é o mesmo. Reescrita de redação passa ilesa — o que não
    passa é a assimetria.
    """
    doc_ts, doc_py = docs
    termos = _termos_do_contrato()
    citados_ts = {t for t in termos if _menciona(doc_ts, t)}
    citados_py = {t for t in termos if _menciona(doc_py, t)}

    assert citados_ts == citados_py, (
        "as docstrings de ClientInstruction divergiram sobre o que discutem — "
        f"só em shared/ts: {sorted(citados_ts - citados_py)}, "
        f"só em shared/python: {sorted(citados_py - citados_ts)}. "
        "Os dois `shared/` são um contrato só escrito duas vezes: um termo do "
        "contrato é mencionado nas duas pontas ou em nenhuma."
    )


def test_fallback_text_e_obrigatorio_nas_duas_pontas():
    """A convenção "todo novo `type` também carrega `fallback_text`", mecânica.

    Esta é a única das três regras da docstring que **dá** para representar em
    tipo, e o teste de paridade não a cobre: ele exige que `?` no TS tenha
    default no Pydantic, então `fallback_text?: string` no TS com default no
    Python passaria por ele — e um cliente diante de um `type` que não reconhece
    ficaria sem nada para responder, que é exatamente o que a convenção existe
    para impedir.
    """
    campo_py = MODELOS_PYTHON["ClientInstruction"].model_fields["fallback_text"]
    assert campo_py.is_required(), (
        "ClientInstruction.fallback_text deixou de ser obrigatório em "
        "shared/python: um cliente antigo diante de um `type` novo perde o que "
        "responder."
    )

    campo_ts = _parse_ts(INDEX_TS.read_text(encoding="utf-8"))["ClientInstruction"][
        "fallback_text"
    ]
    assert not campo_ts["opcional"], (
        "ClientInstruction.fallback_text virou opcional em shared/ts: mesma "
        "quebra da convenção, do lado do cliente."
    )


#: Alvo executável **mínimo** por caractere barrado: cada valor carrega
#: exatamente um dos caracteres de `_APP_PROIBIDO`, e é uma ameaça real.
#:
#: A minimalidade é o ponto todo. `test_abrir_app_recusa_nome_que_nao_seja_nome`
#: usa alvos realistas, e alvo realista carrega **mais de um** caractere barrado
#: (`C:\Windows\cmd.exe` tem `:` e `\`) — então cada caso dele continua sendo
#: recusado mesmo que a guarda encolha, e tirar `\` de `_APP_PROIBIDO` não
#: derruba teste nenhum (verificado). Um caso por caractere, isolado, é o que
#: transforma "a guarda encolheu" em CI vermelho.
_ALVOS_MINIMOS = {
    ":": "spotify:playlist",  # scheme com alvo
    "/": "usr/bin/sh",  # caminho POSIX
    "\\": r"\\servidor\share",  # caminho UNC do Windows
}


@pytest.mark.parametrize(("proibido", "hostil"), sorted(_ALVOS_MINIMOS.items()))
def test_alvo_minimo_de_cada_caractere_barrado_e_recusado(
    client, corpo, auth, llm, proibido, hostil
):
    """Um alvo que só ofende por `proibido` é recusado pela rota."""
    assert [c for c in _ALVOS_MINIMOS if c in hostil] == [proibido], (
        f"o alvo {hostil!r} deixou de ser mínimo: ele tem que ofender só por "
        f"{proibido!r}, senão volta a passar mesmo com a guarda encolhida."
    )

    llm.resposta = ComandoInterpretado(
        acao="abrir_app", parametros={"app": hostil}, resposta_falada="ok"
    )
    acao = client.post("/comando", json=corpo, headers=auth).json()["actions"][0]

    assert acao["status"] == "error", (
        f"{hostil!r} não foi recusado — a invariante de segurança prometida na "
        f"docstring de ClientInstruction depende de {proibido!r} estar barrado."
    )
    assert acao["instruction"] is None, f"{hostil!r} virou instrução no fio"


def test_alvos_minimos_cobrem_exatamente_a_guarda():
    """`_ALVOS_MINIMOS` e `_APP_PROIBIDO` andam juntos, nos dois sentidos.

    Parametrizar só pela constante não bastaria: caractere **removido** da
    guarda apagaria o próprio caso de teste em vez de derrubá-lo — a suíte
    ficaria verde com um teste a menos. A igualdade de conjuntos fecha os dois
    lados: caractere novo na guarda exige um alvo mínimo novo, e caractere
    removido derruba este teste antes de a cobertura desaparecer em silêncio.
    """
    assert set(_ALVOS_MINIMOS) == set(_APP_PROIBIDO), (
        "a guarda de alvo executável e os alvos mínimos divergiram — "
        f"sem alvo mínimo: {sorted(set(_APP_PROIBIDO) - set(_ALVOS_MINIMOS))}, "
        f"sem guarda: {sorted(set(_ALVOS_MINIMOS) - set(_APP_PROIBIDO))}. "
        "Caractere novo em _APP_PROIBIDO precisa de um alvo mínimo aqui; "
        "caractere removido de lá precisa de justificativa, não de silêncio."
    )
