# Escalabilidade das rodadas de agentes — gargalos, opções e recomendação

> Documento de estudo sobre o **processo** de desenvolvimento, não sobre o
> produto. Baseado no que as rodadas realmente produziram — `git log`,
> `git worktree list`, e os registros de coordenação em `.maestri/` (que é
> gitignored, então as citações abaixo são a única forma de esse histórico
> entrar num documento versionado). A recomendação priorizada está na seção 6;
> o que exige aval do Marcus, na seção 7.

## 1. O problema, em números medidos

Fonte: `git log origin/dev` e `git worktree list` em 2026-09-13, mais os
registros de `.maestri/status-geral.md` e `.maestri/prs-para-abrir-*.md`.

- **47 PRs mergeados** em `dev` (contagem de merges "Merge pull request"),
  **228 commits**, concentrados entre 2026-09-02 e 2026-09-11 — com picos de
  92 commits num dia (09-07) e 55 noutro (09-05).
- **Cada um desses PRs foi aberto e mergeado manualmente no navegador**, um
  por um: abrir o link de compare, colar título e descrição preparados pelo
  coordenador, clicar *Update branch*, esperar os 3 checks, mergear — e a cada
  merge, repetir o *Update branch* nos PRs restantes (proteção estrita).
- **32 rascunhos de PR** (`.maestri/pr-pendente-feature-*.md`) foram escritos
  pelo coordenador porque a abertura automática nunca foi possível.
- No pico das rodadas 9+10 havia **8 branches pushadas ao mesmo tempo, nenhum
  PR aberto**, esperando a sessão manual de revisão — e a instrução vigente
  (2026-09-13) é **nenhuma rodada nova até os 3 PRs pendentes entrarem**: a
  latência da revisão humana serializa todo o resto.
- **14 worktrees vivos** hoje, a maioria apontando para branches já mergeadas;
  **33 branches locais** (a maior parte mergeada há rodadas); e o checkout
  principal `C:\dev\shogun` já esteve **62 commits atrás** de `origin/dev`
  (depois 19) — "agentes que partirem dele começam errado", nas palavras do
  próprio `status-geral.md`.

O sistema funciona — 47 PRs em ~10 dias com CI verde obrigatório é um
resultado real. O problema não é capacidade de produção; é que **todo o custo
marginal caiu em cima do Marcus**, no navegador, clique a clique.

## 2. Os gargalos, com a evidência de cada um

### 2.1 `gh` ausente — a limitação mais recorrente do histórico

Verificado de novo neste estudo: `gh: command not found`. O registro se repete
em pelo menos três momentos distantes:

- `.maestri/conflitos-pendentes.md` (2026-09-05): "o `gh` não está instalado
  nesta máquina, então não deu para confirmar se já existe PR aberto";
- `.maestri/status-geral.md` (2026-09-13): "`gh` não está instalado nesta
  máquina, então nenhum PR foi aberto — ficou tudo preparado para abertura
  manual";
- `.maestri/prs-para-abrir-rodada-9.md` (2026-09-13): idem, com os três links
  de compare montados à mão.

O efeito composto: o coordenador gasta uma fração relevante de cada fechamento
de rodada **escrevendo o PR que não pode abrir** (32 rascunhos), e o Marcus
gasta a sessão de revisão **transcrevendo** esses rascunhos para o navegador
antes de começar a revisar de fato. Nenhum dos dois trabalhos é revisão.

### 2.2 O cerimonial de merge sob proteção estrita

A proteção de `dev` exige os 3 checks **e** branch atualizada. Correto e
deliberado — mas com N PRs pendentes, cada merge dispara *Update branch* +
espera de CI nos N−1 restantes. Com os 8 da rodada 9+10, isso é da ordem de
8+7+…+1 ≈ 36 execuções de espera, todas com um humano clicando entre elas. O
`status-geral.md` até ordena a fila "da mais barata para a mais cara de
revisar" por causa disso.

### 2.3 O incidente do checkout compartilhado — resolvido, mas com lições

`C:\dev\shogun` compartilhado entre agentes causou **dois incidentes** numa
mesma rodada (commit alheio na branch errada; troca de branch durante o commit
de outro), um deles exigindo **force-push autorizado** para consertar
histórico (`feature/plano-integracao-mobile`). A norma "worktree isolado por
agente" nasceu daí e está em vigor — este estudo mesmo roda num worktree.
O resíduo do incidente é o gargalo 2.4.

### 2.4 Lixo acumulado de worktrees e branches

A norma do worktree resolveu a segurança e criou faxina: 14 worktrees, 33
branches locais, e o checkout principal desatualizado (§1). O
`status-geral.md` lista a limpeza como pendência "que eu não faço sozinho" —
em parte porque o modo automático dos agentes bloqueia até um
`git pull --ff-only` no checkout principal (registrado lá). Risco concreto: um
agente novo que parta do checkout principal ou de um worktree velho começa de
uma base errada.

### 2.5 A ambiguidade "merge = plano aprovado"

Precedente firmado no PR #17 e repetido no #38: mergear um documento de
decisão **aprova a recomendação dele**. Isso transformou merges de doc em
decisões de arquitetura implícitas — o `status-geral.md` chama de "a armadilha
do precedente" e pede que o Marcus escreva no merge quando a intenção for só
arquivar. É atrito de decisão em cima de cada PR de documento, e já manteve
trabalho parado (o produtor de pendências ficou bloqueado numa ambiguidade
dessas).

### 2.6 O que **não** apareceu como gargalo

Vale registrar o que o histórico **não** mostra: conflito de merge entre
agentes de uma mesma rodada. O coordenador verifica por `merge-tree` par a par
e por interseção de arquivos antes de liberar ("nenhum arquivo aparece em duas
branches", rodadas 9 e 10), e chega a **proibir** as branches de tocar
`CONTEXTO-GERAL.md`/`ROADMAP.md` para não conflitarem — absorvendo ele mesmo a
consolidação de docs depois dos merges. O paralelismo em si está saudável; o
custo dele foi deslocado para o coordenador (consolidação) e para o Marcus
(revisão serial).

## 3. O que já funciona e nenhuma mudança pode quebrar

1. **Revisão humana antes de todo merge.** É a regra de ouro do CLAUDE.md e a
   premissa deste documento — nenhuma opção abaixo a relativiza.
2. **A verificação independente do coordenador.** Ele reproduz suítes na ponta
   de cada branch, reproduz achados de segurança, confere hash de arquivo
   sensível (`shogun.db` byte a byte na rodada 10). Isso é revisão técnica
   real acontecendo **antes** do Marcus — qualquer automação deve alimentá-la,
   não substituí-la.
3. **PRs pequenos, atômicos, com rascunho pronto.** Os 32 `pr-pendente-*.md`
   são exatamente o material que uma revisão rápida precisa; o problema é o
   transporte manual deles, não o formato.
4. **Worktree isolado por agente e trilhas disjuntas por rodada.** As duas
   normas nasceram de incidente e de verificação, respectivamente, e são o que
   permite 3–4 agentes em paralelo sem conflito.

## 4. Opções para reduzir a fricção

### A. Instalar o `gh` com token — resolver a limitação recorrente de verdade

`winget install GitHub.cli` + `gh auth login` (ou um fine-grained PAT com
`contents: read` e `pull_requests: write` só neste repositório). Custo:
minutos, uma vez.

- **Resolve:** abertura de PR vira um comando do coordenador ao fim da rodada
  (`gh pr create --base dev --title ... --body-file .maestri/pr-pendente-....md`)
  — os 32 rascunhos futuros deixam de ser transcritos à mão. De quebra:
  `gh pr list`/`gh pr checks`/`gh pr diff` destravam as opções B e C.
- **Risco:** um token de escrita na máquina onde agentes rodam. Mitigações
  reais: o PAT fine-grained sem `contents: write` **não consegue push nem
  merge** — o pior caso é um PR aberto indevidamente, que é visível e
  reversível; e a norma comportamental continua: **agente não abre PR sem o
  fechamento de rodada prever isso** — a mudança é o coordenador passar a
  abrir, não cada agente.
- **Não resolve:** o tempo de revisão em si, nem o cerimonial de merge (C).
- Nota honesta: a permissão exata de "abrir PR sem poder mergear" via
  fine-grained PAT é leitura de documentação do GitHub, **não testada nesta
  máquina** — testar faz parte da instalação.

### B. Fila de revisão consolidada — um script que monta a mesa de uma vez

Um script pequeno (PowerShell ou Python, no repositório) que, dado
`origin/dev`, liste cada branch pendente com: commits, diffstat, resultado de
`merge-tree`, o `pr-pendente-*.md` correspondente e (com `gh`) o estado de
PR/checks — gerando um único markdown de sessão de revisão. É formalizar o que
o coordenador já faz à mão nos `prs-para-abrir-rodada-*.md`.

- **Resolve:** o Marcus revisa a rodada como **uma sessão**, não como N abas;
  e o índice deixa de depender da disciplina do coordenador de cada rodada.
- **Custo:** baixo (um arquivo, sem dependência nova). **Risco:** quase zero —
  é leitura.
- **Não resolve:** as decisões continuam exigindo o Marcus (e devem); abrir e
  mergear continuam manuais sem A/C.

### C. Tirar o babysitting do merge: `--auto` e (talvez) merge queue

Depois que o Marcus **revisou e aprovou**, o que resta é mecânico: *Update
branch* → esperar CI → clicar merge → repetir nos restantes. Duas formas de
eliminar isso sem tocar na revisão:

- **`gh pr merge --auto --squash` (ou merge) por PR aprovado:** o GitHub
  mergeia sozinho quando os checks passarem. O clique humano passa a ser **um
  por PR** (a aprovação), em vez de dois-a-quatro. Disponível em qualquer
  plano; depende só do `gh` (A).
- **Merge queue** na proteção de `dev`: enfileira os aprovados e resolve o
  *Update branch* em série sozinha. Ressalva de fato **não verificado**: a
  disponibilidade de merge queue para repositório **privado em plano pessoal**
  precisa ser conferida na conta — em leitura de documentação, o recurso é
  limitado a organizações; se for o caso, o `--auto` por PR entrega 80% do
  ganho sem requisito de plano.
- **Risco:** o merge acontece sem um último olhar humano **depois** da
  aprovação — mas esse último olhar já é hoje um clique cego após CI verde. A
  revisão de conteúdo não muda de lugar.
- **Não resolve:** nada sobre a fila de decisões (2.5) nem sobre a faxina (D).

### D. Faxina automatizada de worktrees e branches

Um script de manutenção (rodado pelo coordenador no fim de rodada, ou pelo
Marcus): remover worktrees cujas branches já estão mergeadas
(`git worktree remove` + `git branch -d` só quando `--merged origin/dev`),
e atualizar o checkout principal com `--ff-only`.

- **Resolve:** a classe de erro "agente partiu de base velha" e a lista de
  faxina do `status-geral.md`.
- **Custo:** baixo. **Risco:** baixo se o script só apagar o que está
  comprovadamente mergeado e nunca usar `-D`/força — worktrees com sujeira
  local abortam e ficam para decisão humana. Atenção ao detalhe já registrado:
  o modo automático dos agentes bloqueia operações no checkout principal;
  a execução pode precisar ser do Marcus ou de uma sessão com permissão
  explícita.
- **Não resolve:** nada da revisão; é higiene.

### E. Política explícita de WIP em vez de "zero rodada nova"

A instrução atual ("nenhuma rodada nova até os 3 entrarem") protege contra o
acúmulo — 8 branches pendentes foi peso real. Mas o custo é parar 4 agentes
por latência de revisão. Alternativa: **limite explícito de branches
pendentes** (ex.: no máximo 4), com rodadas novas permitidas só em trilhas
disjuntas das pendentes (verificação que o coordenador já faz por
merge-tree/interseção de arquivos).

- **Resolve:** o pipeline não seca enquanto a revisão espera um dia bom.
- **Risco:** o acúmulo volta se o limite for alto demais; e mais branches
  pendentes = mais *Update branch* (mitigado por C).
- **Não resolve:** o tempo de revisão por PR.

### F. Desambiguar "merge = aprovado" por convenção de título

Uma linha de processo: PRs de documento de decisão passam a declarar no corpo
(o coordenador já escreve os corpos) uma de duas fórmulas fixas — **"merge
aprova a recomendação da seção N"** ou **"merge apenas arquiva; decisões da
seção N continuam abertas"**. Custo zero; elimina a classe de ambiguidade que
já parou trabalho (2.5).

## 5. Mais ou menos agentes por rodada?

A evidência aponta para **manter 3–4, e não é empate técnico**:

- **A produção não é o gargalo.** 8 branches esperando revisão é a prova de
  que os agentes produzem mais do que o funil humano escoa. Mais agentes =
  fila maior, não entrega maior.
- **O paralelismo atual é seguro porque é disjunto por construção.** As
  rodadas 9 e 10 fecharam com zero interseção de arquivos — mas isso custa
  planejamento do coordenador (inclusive proibir toques em docs
  compartilhados, acumulando consolidação para depois). Mais trilhas = mais
  esforço de disjunção e mais consolidação represada.
- **Os incidentes históricos vieram de infraestrutura compartilhada, não do
  número de agentes** — e a causa (checkout único) já foi removida pela norma
  do worktree.
- **Menos agentes desperdiçaria a disjunção real que existe** — servidor,
  desktop, contratos e docs raramente competem pelos mesmos arquivos.
- Padrão que valeu a pena e deve continuar: **agente sem trilha de código vira
  revisor** (o mobile congelado produziu as revisões de contrato que acharam o
  problema do histórico otimista de forma independente do contratos — duas
  fontes chegando ao mesmo achado foi o melhor sinal de que era real).

## 6. Recomendação priorizada (impacto ÷ custo)

| # | Ação | Custo | O que muda para o Marcus | O que NÃO resolve |
|---|---|---|---|---|
| 1 | **Instalar `gh` + PAT fine-grained** (opção A) | minutos, uma vez | a rodada termina com PRs **abertos**, título e corpo já colados; fim da transcrição manual | o tempo de ler e decidir cada PR |
| 2 | **`gh pr merge --auto` após aprovação** (opção C, metade sem requisito de plano) | zero além do #1 | aprovou → esquece; o *Update branch* + espera de CI + clique final somem | a fila de decisões; conflitos (não existem hoje) |
| 3 | **Fila de revisão consolidada** (opção B) | 1 script pequeno | uma página única por rodada com diffstat, rascunho e checks — revisar N PRs numa sentada | abrir/mergear (coberto por 1–2); as decisões em si |
| 4 | **Convenção "aprova × arquiva" nos PRs de decisão** (opção F) | zero | fim da ambiguidade que já parou trabalho; mergear doc deixa de ser decisão implícita | nada técnico — é só clareza |
| 5 | **Script de faxina de worktrees/branches** (opção D) | baixo | agentes nunca mais partem de base velha; a lista de faxina do status-geral zera | nada da revisão |
| 6 | **Limite de WIP explícito no lugar de "zero rodada nova"** (opção E) | zero (é política) | agentes seguem produzindo em trilhas disjuntas enquanto a revisão espera o seu tempo | o tempo de revisão por PR; exige o #2 para não inflar o cerimonial |
| — | **Merge queue na proteção** (opção C, outra metade) | config | eliminaria o *Update branch* em série de vez | **verificar disponibilidade no plano da conta antes de contar com isso** |

Os itens 1+2 são o núcleo: atacam as duas pontas mecânicas (abrir e mergear)
sem tocar na única parte que deve continuar humana — ler, questionar e
aprovar. O item 3 torna essa parte humana mais barata sem diluí-la. Tudo do 4
para baixo é higiene e política, valioso mas não urgente.

O que esta lista deliberadamente **não** contém: qualquer forma de merge sem
aprovação humana, qualquer agente decidindo abrir PR fora do fechamento de
rodada, e qualquer redução da verificação independente do coordenador — os
três são o que mantém a qualidade que os 47 PRs mostraram.

## 7. O que precisa de aval do Marcus

1. **Um token do GitHub na máquina dos agentes** (item 1). É a decisão de
   segurança do documento: o PAT fine-grained proposto não pode dar push nem
   merge, mas "existe um token" é qualitativamente diferente de "não existe".
   Se a resposta for não, os itens 2 e parte do 3 caem junto — e a alternativa
   honesta é aceitar a transcrição manual como custo permanente.
2. **`--auto` no merge após aprovação** (item 2) — o último clique deixa de
   existir; confirmar que a aprovação do PR é o ponto final desejado.
3. **O limite de WIP** (item 6) — substituir "nenhuma rodada até os pendentes
   entrarem" por um teto numérico é mudança de uma instrução sua; o número
   (sugestão: 4) também é seu.
4. **A convenção "aprova × arquiva"** (item 4) — muda o significado de um
   merge, que hoje é precedente firmado (#17/#38); só você pode reescrever o
   precedente.
5. **Quem roda a faxina** (item 5) — se o modo automático continuar bloqueando
   operações no checkout principal, o script é seu ou de uma sessão com
   permissão explícita; decidir onde ele vive.
