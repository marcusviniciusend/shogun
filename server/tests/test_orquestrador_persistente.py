"""ShogunOrquestradorProvider com repositório: mesma semântica, agora no banco.

Tudo roda contra SQLite em memória (ou arquivo temporário, no caso da
migração) — nenhum teste toca rede, credencial ou o banco real.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.db import RepositorioPendencias
from app.domain import Pendencia, ShogunOrquestradorProvider, StatusAgente

AGORA = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def repositorio(db) -> RepositorioPendencias:
    return RepositorioPendencias(db)


@pytest.fixture
def provider(repositorio) -> ShogunOrquestradorProvider:
    return ShogunOrquestradorProvider(repositorio=repositorio)


# -- semantica identica a do modo em memoria ---------------------------------


def test_registrar_e_ler_de_volta(provider):
    registrada = provider.registrar_pendencia(
        agente_id="a1",
        agente_nome="Contratos",
        descricao="Assinar contrato",
        prioridade=3,
        timestamp=AGORA,
    )

    assert provider.get_pendencias_agentes() == [registrada]


def test_status_acompanha_o_registro(provider):
    provider.registrar_pendencia(
        "a1", "Contratos", "Travou", status=StatusAgente.TRAVADO, timestamp=AGORA
    )
    assert provider.get_status_agente("a1") == StatusAgente.TRAVADO


def test_agente_desconhecido_e_concluido(provider):
    assert provider.get_status_agente("nao-existe") == StatusAgente.CONCLUIDO


def test_atualizar_status_sem_pendencia_registrada(provider):
    provider.atualizar_status("a9", StatusAgente.EXECUTANDO)
    assert provider.get_status_agente("a9") == StatusAgente.EXECUTANDO
    assert provider.get_pendencias_agentes() == []


def test_ordenacao_global_por_prioridade_e_timestamp(provider):
    provider.registrar_pendencia(
        "a1", "Contratos", "baixa-antiga", prioridade=1, timestamp=AGORA
    )
    provider.registrar_pendencia(
        "a2", "Backend", "alta-nova", prioridade=9, timestamp=AGORA + timedelta(hours=2)
    )
    provider.registrar_pendencia(
        "a3", "Mobile", "alta-antiga", prioridade=9, timestamp=AGORA
    )

    descricoes = [p.descricao for p in provider.get_pendencias_agentes()]
    assert descricoes == ["alta-antiga", "alta-nova", "baixa-antiga"]


def test_limpar_remove_so_o_agente_alvo_e_preserva_status(provider):
    provider.registrar_pendencia(
        "a1", "Contratos", "Do a1", status=StatusAgente.TRAVADO, timestamp=AGORA
    )
    provider.registrar_pendencia("a2", "Backend", "Do a2", timestamp=AGORA)

    provider.limpar_pendencias("a1")

    assert [p.agente_id for p in provider.get_pendencias_agentes()] == ["a2"]
    assert provider.get_status_agente("a1") == StatusAgente.TRAVADO


def test_limpar_agente_desconhecido_nao_falha(provider):
    provider.limpar_pendencias("nao-existe")
    assert provider.get_pendencias_agentes() == []


# -- o que so existe por ser persistente --------------------------------------


def test_estado_sobrevive_a_outra_instancia_do_provider(repositorio):
    """A razão da tarefa: o estado não morre com o objeto — reiniciar o
    servidor (aqui, criar outro provider sobre o mesmo banco) preserva tudo."""
    escritor = ShogunOrquestradorProvider(repositorio=repositorio)
    escritor.registrar_pendencia(
        "a1", "Contratos", "Persistida", prioridade=5, timestamp=AGORA
    )
    escritor.atualizar_status("a1", StatusAgente.ERRO)

    leitor = ShogunOrquestradorProvider(repositorio=repositorio)

    assert [p.descricao for p in leitor.get_pendencias_agentes()] == ["Persistida"]
    assert leitor.get_status_agente("a1") == StatusAgente.ERRO


def test_sem_repositorio_continua_em_memoria():
    """Compatibilidade: o default segue sendo o modo em memória, isolado por
    instância — nada vaza para instância nova."""
    efemero = ShogunOrquestradorProvider()
    efemero.registrar_pendencia("a1", "Contratos", "Some ao reiniciar")

    assert ShogunOrquestradorProvider().get_pendencias_agentes() == []


def test_timestamp_naive_e_lido_como_utc(provider):
    naive = AGORA.replace(tzinfo=None)
    provider.registrar_pendencia("a1", "Contratos", "Sem fuso", timestamp=naive)

    (lida,) = provider.get_pendencias_agentes()
    assert lida.timestamp == AGORA  # aware, mesmo instante


def test_registro_repetido_acumula_e_atualiza_status(provider):
    provider.registrar_pendencia(
        "a1", "Contratos", "Primeira", status=StatusAgente.PENDENTE, timestamp=AGORA
    )
    provider.registrar_pendencia(
        "a1", "Contratos", "Segunda", status=StatusAgente.EXECUTANDO, timestamp=AGORA
    )

    assert len(provider.get_pendencias_agentes()) == 2
    assert provider.get_status_agente("a1") == StatusAgente.EXECUTANDO


def test_repositorio_devolve_dominio_puro(repositorio):
    """A borda do repositório é o vocabulário do domínio, não linha de tabela."""
    repositorio.registrar(
        Pendencia(
            agente_id="a1",
            agente_nome="Contratos",
            status=StatusAgente.PENDENTE,
            descricao="Direto no repositório",
            timestamp=AGORA,
        )
    )

    (pendencia,) = repositorio.listar()
    assert isinstance(pendencia, Pendencia)
    assert pendencia.agente_nome == "Contratos"
    assert pendencia.timestamp.tzinfo is not None


# -- migracao Alembic ----------------------------------------------------------


def test_migracao_sobe_e_desce(tmp_path, monkeypatch):
    """`upgrade head` cria `agentes` e `pendencias`; `downgrade -1` desfaz sem
    tocar nas tabelas anteriores.

    Roda o Alembic de verdade, mas contra um arquivo SQLite temporário — sem
    rede e sem credencial, então continua teste de unidade para efeito do CI.
    `alembic/env.py` lê a URL de `settings`, por isso o monkeypatch é no
    atributo, não na variável de ambiente (o singleton já foi carregado).
    """
    alembic = pytest.importorskip("alembic")  # noqa: F841 — dependência de runtime
    from pathlib import Path

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect

    from app.core.config import settings

    banco = tmp_path / "migracao.db"
    url = "sqlite:///" + banco.as_posix()
    monkeypatch.setattr(settings, "shogun_database_url", url)

    raiz_server = Path(__file__).resolve().parents[1]
    config = Config(str(raiz_server / "alembic.ini"))
    config.set_main_option("script_location", str(raiz_server / "alembic"))

    command.upgrade(config, "head")
    tabelas = set(inspect(create_engine(url)).get_table_names())
    assert {"agentes", "pendencias", "sessions", "messages"} <= tabelas

    command.downgrade(config, "-1")
    tabelas = set(inspect(create_engine(url)).get_table_names())
    assert "agentes" not in tabelas and "pendencias" not in tabelas
    assert {"sessions", "messages", "messages_uso"} <= tabelas
