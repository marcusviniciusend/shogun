# scripts/ — tooling de processo do repositório

Ferramentas de apoio ao fluxo de rodadas/revisão. Nada aqui roda em produção
nem é importado pelo servidor ou pelos clientes.

## `faxina_worktrees.py` — faxina de worktrees e branches mergeadas

Limpa o acúmulo local das rodadas: worktrees de agentes (`C:\dev\shogun-wt-*`,
`.claude/worktrees/*`) já mergeados em `origin/dev` e branches locais em dois
padrões — e nada além deles: `feature/*` cujo remoto sumiu após o merge
(upstream `gone`) e `worktree-agent-*` (criadas pelo harness do Claude Code
para os worktrees dos agentes; quando o worktree é removido, a branch fica
órfã). **Dry-run por padrão** — sem flag nenhuma ele só imprime o plano
("removeria X porque Y") e não toca em nada; quem executa a faxina de verdade
é o humano, com flags explícitas.

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
worktree cair. Com as duas flags juntas a ordem interna já resolve (worktrees
rodam antes das branches); rodando só `--branches`, a branch em uso num
worktree candidato ainda presente é rebaixada para `MANTIDA` com o motivo, em
vez de virar uma recusa previsível do git.

### Critérios de segurança

- Só é candidato o worktree **limpo** (`git status --porcelain` vazio) e com
  a HEAD **já contida em `origin/dev`**; sujo, não contido, `locked` ou em
  `dev`/`main` aparece como `MANTIDO` com o motivo. Diretório que sumiu do
  disco vira caso de `git worktree prune`.
- O checkout principal e o worktree de onde o script roda nunca são tocados.
- Só são candidatas branches em dois padrões, com critérios **assimétricos de
  propósito**:
  - `feature/*`: exige upstream `gone` **e** ponta contida em `origin/dev`.
    "Sem upstream" significa trabalho nunca publicado — fica.
  - `worktree-agent-*`: basta a ponta contida em `origin/dev`. Essas branches
    nunca são pushadas — "sem upstream" é a natureza delas, não um sinal de
    trabalho não publicado, então o critério "sem upstream = mantida" das
    `feature/*` **não** se aplica aqui. (Se uma delas tiver upstream vivo,
    está fora do padrão esperado e fica mantida.)

  Em ambos os padrões a remoção usa `git branch -d` (minúsculo) — o próprio
  git recusa o que não estiver mergeado.
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

### Validação de campo

Primeira execução real em **2026-09-13** (comandada pelo Marcus): **21
worktrees e 39 branches `feature/*` removidos, 0 recusas do git**, exatamente
como o plano do dry-run previa. A execução revelou um resto fora do escopo da
v1: **10 branches `worktree-agent-*` órfãs** (o harness cria a branch junto
com o worktree do agente; remover o worktree deixa a branch para trás),
removidas à mão com `git branch -d` — todas mergeadas, o `-d` confirmou. A
cobertura desses órfãos entrou no script na sequência (esta versão).

## `checar_ambiente_desktop.py` — diagnóstico do build nativo do desktop

Diz por que o `cargo build` do `desktop/src-tauri` vai falhar **antes** de você
esperar a compilação chegar lá. Desde o PR #63 o desktop depende de
`whisper-rs`, cujo build script compila o whisper.cpp com **CMake** e gera os
bindings com **bindgen**, que precisa de uma **libclang**. Nenhum dos dois vem
com o rustup, e os dois falham dentro de um build script — longe do que a
pessoa fez, com mensagem que não diz o que instalar.

**Diagnóstico, não instalação.** O script só lê a máquina: não instala, não
baixa e não escreve variável de ambiente nenhuma. Decisão deliberada — instalar
LLVM (~3 GB, com admin) ou mexer no ambiente do usuário é escolha do dono da
máquina, não de um script de repositório. O que ele faz é tirar a tentativa e
erro do caminho: aponta o que falta, onde a coisa já está escondida na máquina,
e imprime a linha pronta para colar.

O que confere: `cargo`, `npm`, `cmake` (PATH → variável `CMAKE` → CMake
embutido no Visual Studio, que existe mas não entra no PATH) e `libclang`
(`LIBCLANG_PATH` → LLVM de sistema → wheel `libclang` do pip, varrendo **todos**
os Python do PATH, não só o primeiro).

### Como rodar

A partir da raiz do repositório (Python 3.11+, stdlib apenas; Git Bash ou
PowerShell). Sai com **exit 1** enquanto faltar algo.

```bash
python scripts/checar_ambiente_desktop.py             # só o diagnóstico
python scripts/checar_ambiente_desktop.py --exports   # + variáveis prontas para colar
```

Saída real desta máquina antes de configurar qualquer coisa:

```
Ambiente de build do desktop (npm run tauri dev/build)
--------------------------------------------------------
OK     cargo (rustup): C:\Users\vivil\.cargo\bin\cargo.EXE - cargo 1.97.1
OK     npm (Node.js): C:\Program Files\nodejs\npm.cmd - v11.12.1
FALTA  cmake: fora do PATH, mas existe no Visual Studio: C:\Program Files (x86)\...\CMake\bin\cmake.exe
         -> Aponte a variavel CMAKE para ele (ou acrescente a pasta ao PATH) - veja --exports
FALTA  libclang (bindgen): nenhuma libclang na maquina (sem LLVM de sistema, sem wheel do pip)
         -> winget install LLVM.LLVM      # recomendado; precisa de admin e ~3 GB
         -> python -m pip install libclang # alternativa sem admin
--------------------------------------------------------
2 item(ns) faltando - `cargo build` do desktop vai falhar.
```

E depois, com as duas variáveis exportadas (exit 0):

```
OK     cmake: CMAKE=C:\Program Files (x86)\...\cmake.exe - cmake version 3.31.6-msvc6
OK     libclang (bindgen): LIBCLANG_PATH=...\Python314\Lib\site-packages\clang\native -> libclang.dll
--------------------------------------------------------
Tudo pronto. `cargo check` em desktop/src-tauri deve passar.
```

Esse estado verde é o mesmo sob o qual `cargo check` e `cargo build` foram
verificados em 13/09/2026 (`dev` em `8cbd9df`).

### Limites conhecidos

- **Não testa a compilação.** Ele confere presença e legibilidade das
  ferramentas, não se elas funcionam juntas; quem responde isso é
  `cargo clean -p whisper-rs-sys && cargo check`.
- **Escrito para Windows.** Em Linux/macOS ele degrada para "procure no
  gerenciador de pacotes" em vez de dar o comando exato — a máquina de
  desenvolvimento do projeto é Windows, e é lá que as duas falhas doem.
- **Sem teste automatizado no CI** (mesma limitação consciente dos outros dois
  scripts daqui).

O contexto completo — os erros reais de cada ausência, por que o atalho
`WHISPER_DONT_GENERATE_BINDINGS=1` não funciona no Windows, e a ressalva de
amarrar o build a um `site-packages` — está em `desktop/README.md`, seção
"Pré-requisitos de build nativo".

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
