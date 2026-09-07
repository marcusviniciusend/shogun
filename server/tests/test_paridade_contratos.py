"""Paridade entre os contratos de ``shared/python`` e ``shared/ts``.

Hoje nada garante que os modelos Pydantic e as interfaces TypeScript descrevem
o mesmo fio. Estes testes leem ``shared/ts/index.ts`` como texto (parse
estatico, sem Node no CI) e comparam com a introspeccao dos modelos Pydantic.

Limitacoes conhecidas do parse estatico:

- So entende o subconjunto de TypeScript usado hoje no arquivo: blocos
  ``export interface Nome { ... }`` com campos ``nome?: tipo;`` cujo tipo e uma
  uniao de primitivos (``string``, ``number``, ``boolean``, ``null``), literais
  de string, referencias a outras interfaces e arrays ``Tipo[]``. Generics,
  ``type`` aliases, interfaces aninhadas ou ``extends`` nao sao suportados —
  se o index.ts crescer para alem disso, o parser precisa crescer junto (o
  teste falha com "tipo TS nao reconhecido" em vez de passar em silencio).
- O TS nao e compilado: um index.ts sintaticamente invalido que ainda casa com
  as regexes passaria pelo parse. O objetivo aqui e paridade de campos, nao
  validacao de TypeScript.
- Opcionalidade nao e simetrica de proposito: ``?`` no TS exige default no
  Pydantic, mas um default no Pydantic nao exige ``?`` no TS. Exemplo real:
  ``CommandResponse.actions`` tem default ``[]`` no servidor por conveniencia,
  e mesmo assim o cliente pode contar que a chave sempre vem no JSON — no fio
  ela e obrigatoria.
"""

import re
from pathlib import Path
from typing import Literal, get_args, get_origin

from app.core.contracts import AgentAction, CommandRequest, CommandResponse

MODELOS_PYTHON = {
    "AgentAction": AgentAction,
    "CommandRequest": CommandRequest,
    "CommandResponse": CommandResponse,
}

INDEX_TS = Path(__file__).resolve().parents[2] / "shared" / "ts" / "index.ts"

# --- Parse estatico do TypeScript -------------------------------------------

_RE_COMENTARIO_BLOCO = re.compile(r"/\*.*?\*/", re.DOTALL)
_RE_COMENTARIO_LINHA = re.compile(r"//[^\n]*")
_RE_INTERFACE = re.compile(r"export\s+interface\s+(\w+)\s*\{(.*?)\}", re.DOTALL)
_RE_CAMPO = re.compile(r"(\w+)(\?)?\s*:\s*([^;]+);")

_PRIMITIVOS_TS = {"string", "number", "boolean"}


def _normalizar_tipo_ts(texto: str, interfaces: set[str]) -> dict:
    """Reduz um tipo TS a uma forma comparavel: uniao de partes + anulavel."""
    partes = [p.strip() for p in texto.split("|")]
    anulavel = "null" in partes or "undefined" in partes
    partes = [p for p in partes if p not in ("null", "undefined")]

    literais = set()
    primitivos = set()
    arrays = set()
    refs = set()
    for parte in partes:
        if re.fullmatch(r'"[^"]*"', parte):
            literais.add(parte.strip('"'))
        elif parte in _PRIMITIVOS_TS:
            primitivos.add(parte)
        elif parte.endswith("[]"):
            arrays.add(parte[:-2].strip())
        elif parte in interfaces:
            refs.add(parte)
        else:
            raise AssertionError(f"tipo TS nao reconhecido pelo parser: {parte!r}")

    return {
        "anulavel": anulavel,
        "literais": literais,
        "primitivos": primitivos,
        "arrays": arrays,
        "refs": refs,
    }


def _parse_ts(fonte: str) -> dict[str, dict[str, dict]]:
    """{interface: {campo: {"opcional": bool, "tipo": dict}}}"""
    sem_comentarios = _RE_COMENTARIO_LINHA.sub("", _RE_COMENTARIO_BLOCO.sub("", fonte))
    blocos = _RE_INTERFACE.findall(sem_comentarios)
    nomes = {nome for nome, _ in blocos}

    interfaces: dict[str, dict[str, dict]] = {}
    for nome, corpo in blocos:
        campos = {}
        for campo, opcional, tipo in _RE_CAMPO.findall(corpo):
            campos[campo] = {
                "opcional": opcional == "?",
                "tipo": _normalizar_tipo_ts(tipo.strip(), nomes),
            }
        assert campos, f"interface {nome} sem campos reconhecidos — parser desatualizado?"
        interfaces[nome] = campos
    return interfaces


# --- Introspeccao dos modelos Pydantic ---------------------------------------

_PRIMITIVOS_PY = {str: "string", int: "number", float: "number", bool: "boolean"}


def _normalizar_tipo_py(annotation) -> dict:
    """Mesma forma comparavel de `_normalizar_tipo_ts`, a partir da annotation."""
    partes = list(get_args(annotation)) if _e_uniao(annotation) else [annotation]
    anulavel = type(None) in partes
    partes = [p for p in partes if p is not type(None)]

    literais = set()
    primitivos = set()
    arrays = set()
    refs = set()
    for parte in partes:
        if get_origin(parte) is Literal:
            literais.update(get_args(parte))
        elif parte in _PRIMITIVOS_PY:
            primitivos.add(_PRIMITIVOS_PY[parte])
        elif get_origin(parte) is list:
            (item,) = get_args(parte)
            arrays.add(item.__name__)
        elif parte in MODELOS_PYTHON.values():
            refs.add(parte.__name__)
        else:
            raise AssertionError(f"tipo Python nao reconhecido pelo teste: {parte!r}")

    return {
        "anulavel": anulavel,
        "literais": literais,
        "primitivos": primitivos,
        "arrays": arrays,
        "refs": refs,
    }


def _e_uniao(annotation) -> bool:
    import types
    import typing

    return get_origin(annotation) in (types.UnionType, typing.Union)


def _parse_python() -> dict[str, dict[str, dict]]:
    modelos: dict[str, dict[str, dict]] = {}
    for nome, modelo in MODELOS_PYTHON.items():
        modelos[nome] = {
            campo: {
                "obrigatorio": info.is_required(),
                "tipo": _normalizar_tipo_py(info.annotation),
            }
            for campo, info in modelo.model_fields.items()
        }
    return modelos


# --- Testes -------------------------------------------------------------------


def _contratos():
    return _parse_ts(INDEX_TS.read_text(encoding="utf-8")), _parse_python()


def test_mesmos_contratos_dos_dois_lados():
    ts, py = _contratos()
    assert set(ts) == set(py), (
        "shared/ts e shared/python nao exportam os mesmos contratos: "
        f"so no TS: {set(ts) - set(py)}, so no Python: {set(py) - set(ts)}"
    )


def test_mesmos_campos_em_cada_contrato():
    ts, py = _contratos()
    for nome in sorted(set(ts) & set(py)):
        assert set(ts[nome]) == set(py[nome]), (
            f"{nome}: campos divergem — so no TS: {set(ts[nome]) - set(py[nome])}, "
            f"so no Python: {set(py[nome]) - set(ts[nome])}"
        )


def test_opcionalidade_coerente():
    """`?` no TS exige default no Pydantic; campo obrigatorio no Pydantic exige
    campo obrigatorio no TS. A volta (default no Pydantic com campo obrigatorio
    no TS) e permitida — ver docstring do modulo."""
    ts, py = _contratos()
    for nome in sorted(set(ts) & set(py)):
        for campo in sorted(set(ts[nome]) & set(py[nome])):
            if ts[nome][campo]["opcional"]:
                assert not py[nome][campo]["obrigatorio"], (
                    f"{nome}.{campo} e opcional no TS mas obrigatorio no Pydantic"
                )


def test_tipos_equivalentes():
    ts, py = _contratos()
    for nome in sorted(set(ts) & set(py)):
        for campo in sorted(set(ts[nome]) & set(py[nome])):
            assert ts[nome][campo]["tipo"] == py[nome][campo]["tipo"], (
                f"{nome}.{campo}: tipos divergem — "
                f"TS {ts[nome][campo]['tipo']} != Python {py[nome][campo]['tipo']}"
            )
