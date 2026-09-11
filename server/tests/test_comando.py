"""Testes da rota POST /comando — os 8 casos validados no smoke test."""

from app.core.llm import ComandoInterpretado
from app.core.pendencias import get_pendencias_provider
from app.domain import MaestriProvider, StatusAgente

from .conftest import PendenciasFake, _pendencia


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_sem_credenciais_retorna_401(client, corpo):
    assert client.post("/comando", json=corpo).status_code == 401


def test_token_invalido_retorna_401(client, corpo):
    resposta = client.post(
        "/comando", json=corpo, headers={"Authorization": "Bearer errado"}
    )
    assert resposta.status_code == 401


def test_acao_conversar_usa_resposta_livre(client, corpo, auth, llm):
    resposta = client.post("/comando", json=corpo, headers=auth)

    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["session_id"] == "s1"
    assert dados["text"] == "Olá, Marcus."
    assert dados["actions"] == []
    assert llm.chamadas == ["bom dia"]


def test_acao_consultar_pendencias_lista_itens(client, corpo, auth, llm):
    llm.resposta = ComandoInterpretado(
        acao="consultar_pendencias", parametros={}, resposta_falada="ok"
    )

    dados = client.post("/comando", json=corpo, headers=auth).json()

    assert "Assinar contrato (Contratos)" in dados["text"]
    assert "Ligar pro contador (Contratos)" in dados["text"]
    # A de maior prioridade vem primeiro, mesmo o contrato não prometendo ordem.
    assert dados["text"].index("Assinar contrato") < dados["text"].index("Ligar pro")
    assert dados["actions"] == [
        {
            "agent": "pendencias",
            "status": "ok",
            "detail": "2 pendências",
            # Sem execução delegada: a chave vem no fio, mas nula.
            "instruction": None,
        }
    ]


def test_acao_abrir_app_delega_ao_cliente(client, corpo, auth, llm):
    """O servidor não executa nada: devolve a ClientInstruction na action."""
    llm.resposta = ComandoInterpretado(
        acao="abrir_app", parametros={"app": "Spotify"}, resposta_falada="ok"
    )

    dados = client.post("/comando", json=corpo, headers=auth).json()

    assert "Spotify" in dados["text"]
    acao = dados["actions"][0]
    assert acao["agent"] == "sistema"
    assert acao["status"] == "ok"
    assert acao["instruction"] == {
        "type": "open_app",
        "app": "Spotify",
        "fallback_text": "Não consegui abrir o Spotify neste aparelho, Marcus.",
    }


def test_abrir_app_sem_parametro_nao_gera_instrucao(client, corpo, auth, llm):
    """LLM sem `app` nos parâmetros: erro explicado, nenhuma instrução no fio."""
    llm.resposta = ComandoInterpretado(
        acao="abrir_app", parametros={}, resposta_falada="ok"
    )

    dados = client.post("/comando", json=corpo, headers=auth).json()

    assert "qual aplicativo" in dados["text"]
    acao = dados["actions"][0]
    assert acao["status"] == "error"
    assert acao["instruction"] is None


def test_comando_vazio_retorna_422(client, corpo, auth):
    resposta = client.post("/comando", json={**corpo, "text": "   "}, headers=auth)
    assert resposta.status_code == 422


def test_provedor_que_falha_nao_afirma_que_esta_em_dia(client, corpo, auth, llm):
    """Fonte quebrada não pode virar "você não tem pendências" — seria mentir."""
    from app.main import app

    # MaestriProvider ainda levanta NotImplementedError (API do Maestri indefinida).
    app.dependency_overrides[get_pendencias_provider] = lambda: MaestriProvider(
        base_url="http://maestri.local"
    )
    llm.resposta = ComandoInterpretado(
        acao="consultar_pendencias", parametros={}, resposta_falada="ok"
    )

    dados = client.post("/comando", json=corpo, headers=auth).json()

    assert "Não consegui consultar" in dados["text"]
    assert dados["actions"][0]["status"] == "error"


def test_llm_indisponivel_retorna_503(client, corpo, auth, llm):
    llm.erro = "sem chave"
    resposta = client.post("/comando", json=corpo, headers=auth)
    assert resposta.status_code == 503


#: Mensagem plantada nas exceções dos testes de vazamento. Imita o que uma
#: exceção real carregaria: caminho de arquivo, driver de banco, URL interna.
_SEGREDO = "/srv/shogun/.env psycopg2 http://maestri.interno:8080/api"


def test_falha_do_provedor_nao_vaza_a_excecao_no_detail(client, corpo, auth, llm):
    """O detail vai para o cliente; a mensagem crua da exceção, só para o log."""
    from app.main import app

    class ProvedorQuebrado(PendenciasFake):
        def get_pendencias_agentes(self):
            raise RuntimeError(_SEGREDO)

    app.dependency_overrides[get_pendencias_provider] = lambda: ProvedorQuebrado()
    llm.resposta = ComandoInterpretado(
        acao="consultar_pendencias", parametros={}, resposta_falada="ok"
    )

    dados = client.post("/comando", json=corpo, headers=auth).json()

    acao = dados["actions"][0]
    assert acao["status"] == "error"
    # Nem no detail, nem na fala: o segredo não sai do servidor por caminho nenhum.
    corpo_inteiro = repr(dados)
    for pedaco in _SEGREDO.split():
        assert pedaco not in corpo_inteiro
    # E o detail continua dizendo algo — não pode virar string vazia.
    assert acao["detail"]


def test_llm_indisponivel_nao_vaza_a_excecao_no_detail(client, corpo, auth, llm):
    """A mensagem do LLMIndisponivelError expõe endpoint e modelo — fica no log."""
    llm.erro = _SEGREDO

    resposta = client.post("/comando", json=corpo, headers=auth)

    assert resposta.status_code == 503
    detail = resposta.json()["detail"]
    for pedaco in _SEGREDO.split():
        assert pedaco not in detail
    assert detail


def test_sem_pendencias_registradas_nao_inventa_nada(client, corpo, auth, llm):
    from app.main import app

    app.dependency_overrides[get_pendencias_provider] = lambda: PendenciasFake([])
    llm.resposta = ComandoInterpretado(
        acao="consultar_pendencias", parametros={}, resposta_falada="ok"
    )

    dados = client.post("/comando", json=corpo, headers=auth).json()

    assert dados["text"] == "Nenhuma pendência registrada, Marcus."
    assert dados["actions"][0]["detail"] == "0 pendências"


def test_status_critico_aparece_na_fala(client, corpo, auth, llm):
    from app.main import app

    app.dependency_overrides[get_pendencias_provider] = lambda: PendenciasFake(
        [_pendencia("Deploy parado", status=StatusAgente.TRAVADO)]
    )
    llm.resposta = ComandoInterpretado(
        acao="consultar_pendencias", parametros={}, resposta_falada="ok"
    )

    dados = client.post("/comando", json=corpo, headers=auth).json()

    assert "Deploy parado (Contratos, travado)" in dados["text"]
    assert "1 pendência:" in dados["text"]


def test_limite_e_aplicado_localmente(client, corpo, auth, llm):
    """get_pendencias_agentes() não aceita limite; o corte é nosso."""
    from app.main import app

    app.dependency_overrides[get_pendencias_provider] = lambda: PendenciasFake(
        [_pendencia(f"Tarefa {i}", prioridade=i) for i in range(5)]
    )
    llm.resposta = ComandoInterpretado(
        acao="consultar_pendencias", parametros={"limite": 2}, resposta_falada="ok"
    )

    dados = client.post("/comando", json=corpo, headers=auth).json()

    # O total real é preservado — o corte é só da fala.
    assert "Você tem 5 pendências. As 2 mais urgentes:" in dados["text"]
    assert "Tarefa 4" in dados["text"] and "Tarefa 0" not in dados["text"]
    assert dados["actions"][0]["detail"] == "5 pendências"


def test_chamada_sincrona_do_provider_nao_bloqueia_o_event_loop(client, corpo, auth, llm):
    """get_pendencias_agentes() é síncrono e vai para a threadpool."""
    import threading

    threads: list[str] = []

    class Espiao(PendenciasFake):
        def get_pendencias_agentes(self):
            threads.append(threading.current_thread().name)
            return super().get_pendencias_agentes()

    from app.main import app

    app.dependency_overrides[get_pendencias_provider] = lambda: Espiao()
    llm.resposta = ComandoInterpretado(
        acao="consultar_pendencias", parametros={}, resposta_falada="ok"
    )

    client.post("/comando", json=corpo, headers=auth)

    assert threads and all("anyio" in nome.lower() for nome in threads), threads
