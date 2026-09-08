"""Checagem de migracao no startup — o banco tem que estar na head do Alembic.

Motivo: um deploy subiu sem `alembic upgrade head` e toda rota que tocava a
tabela nova respondia 500 — erro descoberto pelo cliente, em producao. A
divergencia e detectavel no boot com uma consulta barata, entao e ali que ela
tem que aparecer.

Decisao: com migracao pendente o servidor RECUSA SUBIR, seguindo o precedente
do token exposto (`ConfiguracaoInseguraError`): e melhor nao subir do que
subir quebrado — um processo de pe respondendo 500 nas rotas de banco parece
saudavel no /health e engana o supervisor. A mensagem de erro diz exatamente o
comando a rodar. `SHOGUN_CHECAR_MIGRACOES=0` desliga a checagem (testes com
banco em memoria e cenarios de diagnostico).
"""

from pathlib import Path

from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

#: server/alembic — este arquivo vive em server/app/db/.
_DIR_ALEMBIC = Path(__file__).resolve().parents[2] / "alembic"


class MigracaoPendenteError(RuntimeError):
    """O schema do banco nao corresponde ao que o codigo espera.

    Levantada no startup, antes de o servidor escutar — como
    `ConfiguracaoInseguraError`, e um erro de operacao, nao de runtime.
    """


def head_do_alembic() -> str:
    """A revisao mais recente dos scripts de migracao (a head unica)."""
    return ScriptDirectory(str(_DIR_ALEMBIC)).get_current_head()


def revisao_do_banco(engine: Engine) -> str | None:
    """A revisao aplicada no banco; `None` quando o Alembic nunca rodou."""
    with engine.connect() as conexao:
        if not inspect(conexao).has_table("alembic_version"):
            return None
        return conexao.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar()


def verificar_migracoes(engine: Engine) -> None:
    """Levanta :class:`MigracaoPendenteError` se o banco nao esta na head."""
    head = head_do_alembic()
    aplicada = revisao_do_banco(engine)
    if aplicada == head:
        return

    estado = (
        f"esta na revisao '{aplicada}'"
        if aplicada is not None
        else "nunca foi migrado (tabela alembic_version ausente)"
    )
    raise MigracaoPendenteError(
        f"O banco ({engine.url}) {estado}, mas o codigo espera a revisao "
        f"'{head}'. Rode a migracao antes de subir o servidor:\n"
        "    cd server && alembic upgrade head\n"
        "Para subir mesmo assim (diagnostico), use SHOGUN_CHECAR_MIGRACOES=0."
    )
