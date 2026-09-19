# L2 — Módulo `server/`

Servidor central. Python 3.11+ e FastAPI. **Único componente com lógica de
negócio real.** Detalhe operacional (endpoints, env vars, provedores) em
[`server/README.md`](../../server/README.md).

## Mapa

```
app/
  main.py                # entrypoint FastAPI (/health + routers)
  api/                   # rotas HTTP
    comando.py           #   POST /comando — o coração
    consumo.py           #   rastreamento de tokens e custo
    pendencias.py        #   status dos agentes
    sessoes.py           #   histórico de conversas
  core/
    config.py            # Settings (pydantic-settings, lê .env)
    contracts.py         # ponte para shared/python (ajusta sys.path)
    security.py          # autenticação Bearer
    pendencias.py        # injeção do PendenciasProvider no FastAPI
    persistencia.py      # SQLAlchemy
    rate_limit.py        # limite por cliente
    rede.py              # cliente HTTP compartilhado
    llm/
      base.py            # Protocol LLMProvider, SYSTEM_PROMPT, SEMANTICA_ACOES, ESQUEMA_COMANDO
      registry.py        # PROVIDERS: nome de config → classe
      fallback.py        # FallbackLLMProvider
      aquecimento.py     # warm-up do provedor
      historico.py       # contexto de conversa
      precos.py          # tabela de preço por modelo
      claude.py · openai_compat.py · ollama.py · deterministico.py
  db/
    engine.py · models.py · repositorio.py · migracao.py   # SQLAlchemy + Alembic
  domain/                # domínio puro — sem HTTP, sem FastAPI
    pendencias.py        # StatusAgente, Pendencia, PendenciasProvider (ABC)
    providers/
      maestri.py                 # placeholder da API do Maestri (ainda indefinida)
      shogun_orquestrador.py     # implementação própria, persistente
  agents/                # agentes especializados (a construir)
tests/                   # pytest — conftest.py tem as fixtures
```

## Provedores de LLM

`PROVIDERS` (`core/llm/registry.py`) mapeia nome → classe:

| Nome de config | Classe | Nota |
|---|---|---|
| `claude` | `ClaudeProvider` | |
| `deepseek`, `openai_mini` | `openai_compat.py` | |
| `ollama` | `OllamaProvider` | local; modelo atual `qwen2.5:7b-instruct` |
| `deterministico` | `DeterministicoProvider` | palavras-chave, sem credencial; **nunca** levanta `LLMIndisponivelError` → fallback final que sempre responde |

`FallbackLLMProvider` envolve o principal quando `SHOGUN_LLM_FALLBACK_PROVIDER`
está preenchido. Escolher provedor e fallback é **só variável de ambiente** —
nenhuma rota conhece implementação concreta.

## Cuidados

- `domain/` não importa `api/` nem FastAPI. Nunca.
- A rota depende da **interface**; a troca é por `app.dependency_overrides`.
- Toda falha de LLM vira `LLMIndisponivelError`.
- `SYSTEM_PROMPT` e `ESQUEMA_COMANDO` são compartilhados — mexer neles muda o
  comportamento de **todos** os provedores de uma vez.
- O significado das ações é **um texto só**: `SEMANTICA_ACOES`. O
  `ESQUEMA_COMANDO` e a `DICA_ESQUEMA` derivam dele, porque o schema não chega
  em todos os provedores (deepseek não recebe schema; o ollama recebe como
  gramática, que garante forma e não semântica). Editar a semântica em qualquer
  um dos dois canais é o erro — ver [`../decisions.md`](../decisions.md),
  2026-09-19.
- Desde o #28 o servidor **recusa subir com migração pendente**:
  `alembic upgrade head`.
- Testes: `cd server && pytest`. Nenhum teste chama API real.
