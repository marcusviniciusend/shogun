"""Testes do módulo de domínio: contrato, providers e serialização.

Nada aqui toca em rede, banco ou FastAPI — o domínio é puro por construção, e os
testes existem justamente para manter essa fronteira honesta.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.domain import (
    MaestriProvider,
    Pendencia,
    PendenciasProvider,
    ShogunOrquestradorProvider,
    StatusAgente,
)

AGORA = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)


# -- contrato ---------------------------------------------------------------


def test_provider_abstrato_nao_instancia():
    with pytest.raises(TypeError) as erro:
        PendenciasProvider()
    assert "abstract" in str(erro.value).lower()


def test_subclasse_incompleta_nao_instancia():
    """Implementar só metade do contrato não basta."""

    class MeioProvider(PendenciasProvider):
        def get_pendencias_agentes(self):
            return []

    with pytest.raises(TypeError):
        MeioProvider()


def test_providers_concretos_implementam_o_contrato():
    assert issubclass(MaestriProvider, PendenciasProvider)
    assert issubclass(ShogunOrquestradorProvider, PendenciasProvider)


# -- ShogunOrquestradorProvider: escrita ------------------------------------


@pytest.fixture
def provider() -> ShogunOrquestradorProvider:
    return ShogunOrquestradorProvider()


def test_registrar_pendencia_devolve_e_armazena(provider):
    pendencia = provider.registrar_pendencia(
        agente_id="a1",
        agente_nome="Contratos",
        descricao="Assinar contrato",
        prioridade=3,
        timestamp=AGORA,
    )

    assert pendencia.agente_id == "a1"
    assert pendencia.status == StatusAgente.PENDENTE  # default
    assert pendencia.prioridade == 3
    assert provider.get_pendencias_agentes() == [pendencia]


def test_registrar_pendencia_sem_timestamp_usa_agora(provider):
    antes = datetime.now(timezone.utc)
    pendencia = provider.registrar_pendencia("a1", "Contratos", "Sem timestamp")
    assert antes <= pendencia.timestamp <= datetime.now(timezone.utc)


def test_registrar_pendencia_reflete_status_do_agente(provider):
    provider.registrar_pendencia("a1", "Contratos", "Travou", status=StatusAgente.TRAVADO)
    assert provider.get_status_agente("a1") == StatusAgente.TRAVADO


def test_registrar_acumula_pendencias_do_mesmo_agente(provider):
    provider.registrar_pendencia("a1", "Contratos", "Primeira", timestamp=AGORA)
    provider.registrar_pendencia("a1", "Contratos", "Segunda", timestamp=AGORA)
    assert len(provider.get_pendencias_agentes()) == 2


def test_status_de_agente_desconhecido_e_concluido(provider):
    assert provider.get_status_agente("nao-existe") == StatusAgente.CONCLUIDO


def test_atualizar_status(provider):
    provider.registrar_pendencia("a1", "Contratos", "Rodando", status=StatusAgente.EXECUTANDO)
    provider.atualizar_status("a1", StatusAgente.ERRO)
    assert provider.get_status_agente("a1") == StatusAgente.ERRO


def test_atualizar_status_de_agente_sem_pendencia(provider):
    """O status é independente das pendências; registrar não é pré-requisito."""
    provider.atualizar_status("a9", StatusAgente.EXECUTANDO)
    assert provider.get_status_agente("a9") == StatusAgente.EXECUTANDO
    assert provider.get_pendencias_agentes() == []


def test_limpar_pendencias_remove_apenas_o_agente_alvo(provider):
    provider.registrar_pendencia("a1", "Contratos", "Do a1", timestamp=AGORA)
    provider.registrar_pendencia("a2", "Backend", "Do a2", timestamp=AGORA)

    provider.limpar_pendencias("a1")

    restantes = provider.get_pendencias_agentes()
    assert [p.agente_id for p in restantes] == ["a2"]


def test_limpar_pendencias_preserva_o_status(provider):
    """Limpar a fila não apaga o que sabemos sobre o agente."""
    provider.registrar_pendencia("a1", "Contratos", "Travou", status=StatusAgente.TRAVADO)
    provider.limpar_pendencias("a1")
    assert provider.get_status_agente("a1") == StatusAgente.TRAVADO


def test_limpar_pendencias_de_agente_desconhecido_nao_falha(provider):
    provider.limpar_pendencias("nao-existe")
    assert provider.get_pendencias_agentes() == []


def test_provider_novo_comeca_vazio(provider):
    assert provider.get_pendencias_agentes() == []


# -- ShogunOrquestradorProvider: ordenação ----------------------------------


def test_ordena_por_prioridade_desc_depois_timestamp(provider):
    # Registrados fora de ordem de propósito, para que a ordem final venha da
    # comparação e não da inserção.
    provider.registrar_pendencia(
        "a1", "Contratos", "baixa-antiga", prioridade=1, timestamp=AGORA
    )
    provider.registrar_pendencia(
        "a2", "Backend", "alta-nova", prioridade=9, timestamp=AGORA + timedelta(hours=2)
    )
    provider.registrar_pendencia(
        "a3", "Mobile", "alta-antiga", prioridade=9, timestamp=AGORA
    )
    provider.registrar_pendencia(
        "a4", "Desktop", "baixa-nova", prioridade=1, timestamp=AGORA + timedelta(hours=1)
    )

    descricoes = [p.descricao for p in provider.get_pendencias_agentes()]
    assert descricoes == ["alta-antiga", "alta-nova", "baixa-antiga", "baixa-nova"]


def test_ordenacao_atravessa_agentes_diferentes(provider):
    """A ordenação é global, não por agente — o agrupamento interno é invisível."""
    provider.registrar_pendencia("a1", "Contratos", "p0", prioridade=0, timestamp=AGORA)
    provider.registrar_pendencia("a2", "Backend", "p5", prioridade=5, timestamp=AGORA)
    provider.registrar_pendencia("a1", "Contratos", "p9", prioridade=9, timestamp=AGORA)

    assert [p.descricao for p in provider.get_pendencias_agentes()] == ["p9", "p5", "p0"]


def test_prioridade_negativa_vai_para_o_fim(provider):
    provider.registrar_pendencia("a1", "Contratos", "normal", prioridade=0, timestamp=AGORA)
    provider.registrar_pendencia("a2", "Backend", "adiada", prioridade=-5, timestamp=AGORA)

    assert [p.descricao for p in provider.get_pendencias_agentes()] == ["normal", "adiada"]


def test_get_pendencias_nao_expoe_o_estado_interno(provider):
    provider.registrar_pendencia("a1", "Contratos", "Original", timestamp=AGORA)

    lista = provider.get_pendencias_agentes()
    lista.clear()

    assert len(provider.get_pendencias_agentes()) == 1


# -- MaestriProvider (placeholder) ------------------------------------------


def test_maestri_guarda_a_configuracao():
    p = MaestriProvider(base_url="https://maestri.local/", api_key="k", timeout=2.0)
    assert p.base_url == "https://maestri.local"  # barra final removida
    assert p.api_key == "k"
    assert p.timeout == 2.0


def test_maestri_defaults():
    p = MaestriProvider(base_url="https://maestri.local")
    assert p.api_key is None
    assert p.timeout == 5.0


def test_maestri_get_pendencias_ainda_nao_implementado():
    p = MaestriProvider(base_url="https://maestri.local")
    with pytest.raises(NotImplementedError, match="Maestri"):
        p.get_pendencias_agentes()


def test_maestri_get_status_ainda_nao_implementado():
    p = MaestriProvider(base_url="https://maestri.local")
    with pytest.raises(NotImplementedError, match="Maestri"):
        p.get_status_agente("a1")


# -- Pendencia (Pydantic) ---------------------------------------------------


def test_prioridade_tem_default_zero():
    p = Pendencia(
        agente_id="a1",
        agente_nome="Contratos",
        status=StatusAgente.PENDENTE,
        descricao="Sem prioridade explícita",
        timestamp=AGORA,
    )
    assert p.prioridade == 0


def test_model_dump_json_serializa_status_e_timestamp():
    p = Pendencia(
        agente_id="a1",
        agente_nome="Contratos",
        status=StatusAgente.TRAVADO,
        descricao="Assinar contrato",
        timestamp=AGORA,
        prioridade=7,
    )

    dados = json.loads(p.model_dump_json())

    assert dados == {
        "agente_id": "a1",
        "agente_nome": "Contratos",
        "status": "travado",  # StatusAgente é str-Enum: serializa como valor
        "descricao": "Assinar contrato",
        "timestamp": "2026-09-03T12:00:00Z",
        "prioridade": 7,
    }


def test_pendencia_faz_round_trip_pelo_json():
    original = Pendencia(
        agente_id="a1",
        agente_nome="Contratos",
        status=StatusAgente.ERRO,
        descricao="Round-trip",
        timestamp=AGORA,
        prioridade=2,
    )
    assert Pendencia.model_validate_json(original.model_dump_json()) == original


def test_status_aceita_string_do_enum():
    p = Pendencia(
        agente_id="a1",
        agente_nome="Contratos",
        status="executando",
        descricao="Coerção de string",
        timestamp=AGORA,
    )
    assert p.status is StatusAgente.EXECUTANDO


def test_status_invalido_e_rejeitado():
    with pytest.raises(ValidationError):
        Pendencia(
            agente_id="a1",
            agente_nome="Contratos",
            status="dormindo",
            descricao="Status inexistente",
            timestamp=AGORA,
        )


def test_campo_obrigatorio_ausente_e_rejeitado():
    with pytest.raises(ValidationError):
        Pendencia(agente_id="a1", agente_nome="Contratos", status=StatusAgente.PENDENTE)
