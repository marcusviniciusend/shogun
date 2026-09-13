# scripts/ — tooling de processo do repositório

Ferramentas de apoio ao fluxo de rodadas/revisão. Nada aqui roda em produção
nem é importado pelo servidor ou pelos clientes.

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
