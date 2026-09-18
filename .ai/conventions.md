# L1 — Convenções

**Fonte da verdade:** [`CLAUDE.md`](../CLAUDE.md) §3. Este arquivo é o resumo
operacional. **Não edite aqui sem editar `CLAUDE.md` junto** — divergência entre
os dois é bug de processo.

## Branches

- Branch de trabalho é sempre **`dev`**. Nunca commitar direto em `main`.
- Trabalho novo sai de `dev`, em `feature/<assunto>`.
- Base de todo PR é **`dev`** (a default do GitHub já é `dev` desde 2026-09-10).
- `main` só é promovida por PR de marco (`dev` → `main`).
- Worktree próprio por agente é **obrigatório** — dois incidentes já
  aconteceram com checkout compartilhado.

## Commits

- Conventional commits, em português, **sem acentos na mensagem**:
  `feat(server):`, `fix(desktop):`, `docs(repo):`, `test(server):`, `chore(repo):`.
- **Um commit por escopo.** Código, teste e documentação não vão no mesmo commit.
- Cada commit é **funcional isoladamente**: a suíte passa em qualquer ponto do
  histórico, não só no fim da série.

## Testes

```bash
cd server && pip install -r requirements-dev.txt && pytest
cd desktop && npm ci && npm test
```

- `pytest` a partir de `server/` (`server/pytest.ini`, `asyncio_mode = auto`).
- `vitest` a partir de `desktop/` (`npm test`).
- **Mexeu nos dois, rode os dois.** Sempre a suíte completa, nunca só o arquivo
  que você tocou.
- **Nenhum teste chama API real.** Cliente HTTP mockado nos provedores;
  `app.dependency_overrides` nas rotas. Fixtures em `server/tests/conftest.py`.
- Teste que precisa de credencial ou rede deixou de ser unitário — não entra no
  CI sem decidir antes onde ele vive.
- `cargo test` (20 testes do microfone) **não roda no CI** — só local.

## CI

`.github/workflows/tests.yml`, a cada push e a cada PR para `dev`/`main`.
Três checks obrigatórios e em modo estrito: `pytest (Python 3.11)`,
`pytest (Python 3.13)`, `vitest (desktop)`. Modo estrito = a branch precisa
estar atualizada com `dev`, então cada merge obriga *Update branch* nos PRs
restantes.

## Onde colocar código novo

| O quê | Onde |
|-------|------|
| Contrato / interface de domínio | `server/app/domain/` (puro: Pydantic/ABC, sem FastAPI, sem I/O) |
| Implementação de `PendenciasProvider` | `server/app/domain/providers/` |
| Provedor de LLM novo | `server/app/core/llm/` + entrada em `registry.py` |
| Rota / configuração | `server/app/api/`, `server/app/core/` |
| Contrato usado também pelos clientes | `shared/python` **e** `shared/ts`, na mesma branch |

## Fluxo de trabalho

1. branch a partir de `dev`;
2. implementar;
3. suíte completa verde;
4. commits atômicos, separados por escopo;
5. `git push -u origin feature/<assunto>`;
6. **parar.** O PR é aberto manualmente pelo Marcus; revisão humana é
   obrigatória. **Nenhum agente faz merge.** `gh` não está instalado.

Rascunho de PR vai em `.maestri/pr-pendente-<branch>.md`, com **`base: dev`**
explícito.
