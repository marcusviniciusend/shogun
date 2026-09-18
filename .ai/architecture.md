# L2 — Arquitetura

**Fonte da verdade:** [`docs/architecture.md`](../docs/architecture.md) e
[`server/README.md`](../server/README.md). Este arquivo é o índice de entrada.

## Em uma frase

Um cérebro, vários clientes: servidor central FastAPI concentra inteligência,
memória e orquestração; os clientes capturam áudio, mostram a interface e falam
a resposta.

## Fluxo de um comando

1. cliente captura áudio e transcreve (STT no cliente);
2. `POST /comando` com `CommandRequest` (Bearer token);
3. servidor interpreta a intenção via `LLMProvider` → `{acao, parametros, resposta_falada}`;
4. conforme a ação, consulta provedores/agentes internos;
5. cliente recebe `CommandResponse` e sintetiza em voz (TTS).

## Mapa do monorepo

| Diretório | O quê | Detalhe |
|-----------|-------|---------|
| `server/` | Servidor central (Python 3.11+, FastAPI) | [`modules/server.md`](modules/server.md) |
| `desktop/` | Cliente Tauri (Rust + TS/React) | [`modules/desktop.md`](modules/desktop.md) |
| `mobile/` | Cliente React Native | [`modules/mobile.md`](modules/mobile.md) — **congelado** |
| `shared/` | Contratos, escritos duas vezes (Pydantic + TS) | [`modules/shared.md`](modules/shared.md) |
| `docs/` | Arquitetura e decisões técnicas | — |

Sem empacotamento: não há `pyproject.toml` instalável; o `sys.path` é ajustado
em `server/app/core/contracts.py` e `server/tests/conftest.py`.

## Regras estruturais que não se negociam

- `domain/` **não importa** nada de `api/` nem do FastAPI. A rota depende da
  **interface**, nunca da implementação — a troca é por injeção de dependência
  (`app.dependency_overrides` nos testes).
- Provedor de LLM novo = classe implementando o `Protocol` `LLMProvider` +
  entrada em `PROVIDERS` (`core/llm/registry.py`). Nada mais muda — nem factory,
  nem rota.
- Toda falha de LLM (rede, timeout, rate limit, formato) vira
  `LLMIndisponivelError`. É o que dispara o fallback.
- `SYSTEM_PROMPT` e `ESQUEMA_COMANDO` são compartilhados por todos os provedores:
  trocar de LLM não muda quem o Shogun é.
- `shared/python` e `shared/ts` andam **na mesma branch**, sempre.
  `server/tests/test_paridade_contratos.py` quebra o CI se você esquecer.

## Navegação barata (L2 sem varredura)

`graphify-out/` tem o grafo do repositório: 1925 nós, 3416 arestas, 131
comunidades (gerado em 2026-09-15). Use `GRAPH_REPORT.md` para achar o hub certo
antes de abrir arquivo. Hubs úteis: *Registro e fabrica de LLM*, *Dominio de
pendencias (Maestri)*, *Invariantes e paridade de contratos*, *Ditado e chat do
desktop*, *Captura de microfone (Rust)*.

Como consultar, em ordem de custo: `graphify query "<pergunta>"` →
`GRAPH_REPORT.md` → abrir arquivo. O portal `Portal` no canvas renderiza
`graph.html` (vis-network via CDN, funciona) — é para olhar, não para consultar.

Regenerar: `/graphify` (custa ~330k tokens de input — não regenere à toa).
**O grafo atual é de 2026-09-15**, então não conhece `.ai/` nem o `CLAUDE.md`
reescrito em 18/09. `graphify . --update` re-extrai só o que mudou.
