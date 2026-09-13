# scripts/ — tooling de processo do repositório

Ferramentas de apoio ao fluxo de rodadas/revisão. Nada aqui roda em produção
nem é importado pelo servidor ou pelos clientes.

## `faxina_worktrees.py` — faxina de worktrees e branches mergeadas

Limpa o acúmulo local das rodadas: worktrees de agentes (`C:\dev\shogun-wt-*`,
`.claude/worktrees/*`) já mergeados em `origin/dev` e branches locais
`feature/*` cujo remoto sumiu após o merge (upstream `gone`). **Dry-run por
padrão** — sem flag nenhuma ele só imprime o plano ("removeria X porque Y") e
não toca em nada; quem executa a faxina de verdade é o humano, com flags
explícitas.

Origem: `docs/escalabilidade-rodadas.md`, seção 4, opção D (a pergunta "quem
roda" da seção 7 foi respondida pelo desenho do `fila_revisao.py`: o humano).

### Como rodar

A partir da raiz do repositório (Python 3.11+, stdlib apenas; funciona em
Git Bash e PowerShell). Fluxo recomendado: rodar seco, ler o plano, e só
então rodar com as flags de execução.

```bash
python scripts/faxina_worktrees.py                          # dry-run (padrão)
python scripts/faxina_worktrees.py --no-fetch               # sem git fetch --prune antes
python scripts/faxina_worktrees.py --executar --worktrees   # remove worktrees + prune
python scripts/faxina_worktrees.py --executar --branches    # remove branches (git branch -d)
python scripts/faxina_worktrees.py --executar --worktrees --branches
```

`--executar` sozinho é erro: exige escolher a categoria (`--worktrees` e/ou
`--branches`). Se for rodar as categorias em execuções separadas, worktrees
primeiro — uma branch em uso num worktree candidato só cai depois que o
worktree cair.

### Critérios de segurança

- Só é candidato o worktree **limpo** (`git status --porcelain` vazio) e com
  a HEAD **já contida em `origin/dev`**; sujo, não contido, `locked` ou em
  `dev`/`main` aparece como `MANTIDO` com o motivo. Diretório que sumiu do
  disco vira caso de `git worktree prune`.
- O checkout principal e o worktree de onde o script roda nunca são tocados.
- Só é candidata a branch `feature/*` com upstream `gone` e ponta contida em
  `origin/dev`. A remoção usa `git branch -d` (minúsculo) — o próprio git
  recusa o que não estiver mergeado.
- O script **nunca** usa `-D`, `--force`, push ou deleção remota; o que o
  git recusar (ex.: worktree que sujou entre a coleta e a remoção) fica
  mantido, logado, e vira exit 1.

### Limites conhecidos

- O critério depende de `origin/dev` atualizado: por padrão roda
  `git fetch --prune origin` antes (é o prune que produz o `gone`); com
  `--no-fetch` a classificação usa o estado local, que pode estar defasado.
- Worktree `locked` de agente encerrado precisa de `git worktree unlock`
  manual antes de entrar na faxina — o script não destrava nada.
- **Sem teste automatizado no CI** (mesma limitação consciente do
  `fila_revisao.py`); o caminho destrutivo foi validado em repositório
  descartável.

## `fila_revisao.py` — fila de revisão consolidada

Gera uma página única em markdown com tudo que a sessão de revisão precisa:
branches `origin/feature/*` pendentes (commits à frente, diffstat, merge limpo
ou não via `merge-tree`, distância do `dev`, link de compare com base `dev`
fixada, rascunho `.maestri/pr-pendente-*.md` correspondente) e os PRs abertos
com seus check-runs, via API pública do GitHub. Leitura apenas — não abre nem
mergeia nada.

Origem: `docs/escalabilidade-rodadas.md`, seção 4, opção B (item 3 da
priorização da seção 6).

### Como rodar

A partir da raiz do repositório (Python 3.11+, stdlib apenas; funciona em
Git Bash e PowerShell):

```bash
python scripts/fila_revisao.py                        # imprime no stdout
python scripts/fila_revisao.py --offline              # pula a API de propósito
python scripts/fila_revisao.py --no-fetch             # não roda git fetch antes
python scripts/fila_revisao.py --out .maestri/fila-revisao.md
```

A saída via `--out` é artefato de sessão, não versionada (`.maestri/` é
gitignored).

### Limites conhecidos

- **API sem token: 60 requisições/hora** (repositório público, leitura
  anônima). O script gasta 1 requisição para listar PRs + 1 por PR para os
  checks. Estourar o limite (ou ficar sem rede) **não derruba o script**: a
  seção só-git sai completa e a de PRs degrada com aviso do que ficou de fora.
  Se um dia houver token na máquina (decisão em aberto —
  `docs/escalabilidade-rodadas.md` §7), nada muda no script: o ganho seria só
  o rate limit maior.
- `git merge-tree --write-tree` requer git >= 2.38; git mais antigo recebe
  mensagem clara de indisponibilidade em vez de crash.
- **Sem teste automatizado no CI** (limitação consciente): o CI do projeto
  roda pytest de `server/` e vitest de `desktop/`; se tooling ganha CI próprio
  é decisão do Marcus.
