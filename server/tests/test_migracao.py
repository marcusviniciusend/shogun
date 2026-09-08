"""Testes da checagem de migracao do startup — SQLite em memoria, sem rede."""

from pathlib import Path

import pytest
from sqlalchemy import text

from app.db import criar_engine
from app.db.migracao import (
    MigracaoPendenteError,
    head_do_alembic,
    revisao_do_banco,
    verificar_migracoes,
)


def _com_revisao(engine, revisao: str) -> None:
    """Grava a revisao como o Alembic gravaria."""
    with engine.begin() as conexao:
        conexao.execute(
            text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        )
        conexao.execute(
            text("INSERT INTO alembic_version VALUES (:rev)"), {"rev": revisao}
        )


def test_head_e_uma_revisao_que_existe_nos_scripts():
    """A head vem dos arquivos de versao reais, nao de valor fixado no codigo."""
    versoes = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    arquivos = " ".join(p.name for p in versoes.glob("*.py"))

    assert head_do_alembic() in arquivos


def test_banco_nunca_migrado_nao_tem_revisao():
    assert revisao_do_banco(criar_engine("sqlite://")) is None


def test_banco_na_head_passa_na_checagem():
    engine = criar_engine("sqlite://")
    _com_revisao(engine, head_do_alembic())

    verificar_migracoes(engine)  # nao levanta


def test_banco_nunca_migrado_recusa_subir_com_o_comando_na_mensagem():
    with pytest.raises(MigracaoPendenteError) as exc:
        verificar_migracoes(criar_engine("sqlite://"))

    mensagem = str(exc.value)
    assert "alembic upgrade head" in mensagem
    assert "nunca foi migrado" in mensagem


def test_banco_em_revisao_antiga_recusa_subir_citando_as_duas_revisoes():
    engine = criar_engine("sqlite://")
    _com_revisao(engine, "rev-antiga")

    with pytest.raises(MigracaoPendenteError) as exc:
        verificar_migracoes(engine)

    mensagem = str(exc.value)
    assert "rev-antiga" in mensagem
    assert head_do_alembic() in mensagem
    assert "alembic upgrade head" in mensagem


def test_checagem_vem_ligada_por_padrao(monkeypatch):
    """SHOGUN_CHECAR_MIGRACOES so e desligada explicitamente (testes, diagnostico)."""
    from app.core.config import Settings

    # O conftest desliga a checagem via ambiente para o TestClient; aqui o
    # interesse e o default de Settings, entao a variavel sai do caminho.
    monkeypatch.delenv("SHOGUN_CHECAR_MIGRACOES", raising=False)

    assert Settings(_env_file=None).shogun_checar_migracoes is True
