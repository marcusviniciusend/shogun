# Mapa de apps configurável no desktop — opções, trade-offs e recomendação

> Documento de decisão, escrito **antes** de qualquer implementação. A
> recomendação explícita está na seção 8; o que ela ainda exige de aprovação
> humana está na seção 9. Nenhuma linha de código, contrato ou permissão muda
> neste documento.

## 1. O buraco

O comentário de `desktop/src/lib/instrucoes.ts` diz, sobre `APPS_CURADOS`:

> Mapa curado nome -> comando do escopo shell. Pequeno de propósito;
> **configurável fica para depois.**

"Depois" virou item de backlog, citado três vezes em
[`acao-resultado.md`](acao-resultado.md) (seções 1c, 5 e 8) como algo que um dia
entra. Este documento é a tentativa de executá-lo — e o achado principal é que
**o item, como está escrito, mistura duas coisas de valor muito diferente, e a
que tem valor real não é configuração.**

O mapa de hoje tem quatro entradas:

| chave | comando | executável + args (via `capabilities/default.json`) |
|---|---|---|
| `navegador` | `abrir-navegador` | `explorer.exe https://www.google.com` |
| `explorer` | `abrir-explorer` | `explorer.exe` (sem args) |
| `calculadora` | `abrir-calculadora` | `calc.exe` (sem args) |
| `spotify` | `abrir-spotify` | `explorer.exe spotify:` |

Mais sete sinônimos compilados (`browser`, `chrome`, `internet`, `arquivos`,
`explorador de arquivos`, `gerenciador de arquivos`, `calc`).

Quando alguém diz "quero o mapa de apps configurável", quer dizer, em ordem de
frequência esperada:

1. **"Quero que o Shogun abra o Discord / o VS Code / a Steam."** — adicionar um
   app **novo**.
2. "Quero que ele entenda *o meu* jeito de chamar o que ele já abre." —
   apelidos.
3. "Não tenho Spotify instalado; quero que ele pare de tentar." — desligar uma
   entrada.

**(1) é o que motiva o item, e (1) é precisamente o que a invariante de
segurança proíbe ser configuração.** (2) e (3) são implementáveis com custo
baixo — e, sozinhos, não fecham o item. É essa assimetria que este documento
existe para tornar explícita antes de alguém escrever código.

## 2. As duas travas — o teto de qualquer opção

Nenhuma opção abaixo pode tocar nestas duas. Elas não são detalhe de
implementação; são a razão de a feature ter o desenho que tem.

**Trava 1 — o servidor manda só o NOME.** `_abrir_app`
(`server/app/api/comando.py`) recusa, **antes de virar instrução**, qualquer
`app` que contenha `:`, `/` ou `\` (`_APP_PROIBIDO`, PR #41). A `ClientInstruction`
carrega um nome simples, e só. Executável, args e URI saem **sempre** do mapa
curado local. String vinda do servidor nunca chega ao `spawn`.

**Trava 2 — o escopo do `tauri-plugin-shell` fixa executável e args por comando
nomeado.** Em `capabilities/default.json`, `shell:allow-spawn` declara quatro
entradas com `cmd` literal e `args` literal (ou `false` = nenhum argumento
permitido). `Command.create(nome, args)` só funciona se `nome` for um dos quatro
**e** os `args` baterem exatamente com os declarados. Ou seja: **nem o próprio
código TypeScript consegue rodar outra coisa.** A trava 1 protege contra o
servidor; a trava 2 protege contra o cliente — inclusive contra um bug nosso.

A lição registrada no próprio comentário do arquivo — *"a permissão no
capabilities é parte da feature, não detalhe"* — vem do incidente do escopo
`http`. Vale repetir aqui porque toda opção interessante deste documento passa
por mexer nesse arquivo.

E há uma terceira peça que amarra as duas: `instrucoes.escopo.test.ts` verifica
**igualdade bidirecional** entre `APPS_CURADOS` e o escopo do capabilities —
comando órfão de qualquer um dos lados quebra o teste. É a única rede mecânica
sobre um acoplamento que é por string, que o `tsc` não vê e que o `cargo` não
vê. Qualquer opção precisa dizer o que acontece com esse teste.

## 3. O que já existe, e que qualquer opção deve reaproveitar

| Peça | Onde | Estado |
|---|---|---|
| `APPS_CURADOS` (nome → comando + args) | `desktop/src/lib/instrucoes.ts` | pronto, 4 entradas |
| `SINONIMOS` compilados | mesmo arquivo | pronto, 7 entradas |
| `normalizar()` (minúsculas, sem acento, espaços colapsados) | mesmo arquivo | pronto, com 6 casos de teste |
| Escopo `shell:allow-spawn` | `src-tauri/capabilities/default.json` | pronto, 4 permissões |
| Guarda `_APP_PROIBIDO` no servidor | `server/app/api/comando.py` | pronta (PR #41) |
| Persistência local (`tauri-plugin-store`, `shogun.json`) | `desktop/src/lib/config.ts` | pronta — 4 chaves + `sessionId` |
| Padrão de validação de valor inválido no store | `carregarConfig()` (o caso do `tema`) | pronto — **é o molde a seguir** |
| Tela de Config | `desktop/src/components/Configuracoes.tsx` | pronta, com `fieldset`/`radiogroup` reaproveitáveis |
| Rede mecânica do acoplamento | `instrucoes.escopo.test.ts` | pronta |
| Rede mecânica da regra de consumo | `instrucoes.test.ts` (7 casos) | pronta |

Duas observações que condicionam o resto:

1. **O `config.ts` já tem o molde de "valor inválido no store cai no default".**
   O tratamento do `tema` (`TEMAS.includes(...)`) existe exatamente porque um
   valor de versão antiga ou de edição manual não pode virar estado que o resto
   do app não conhece. Qualquer configuração de apps herda esse molde — e o
   herda com mais razão, porque o estado em questão desemboca no `spawn`.
2. **`shogun.json` é um arquivo em `%APPDATA%`, não um canal autenticado.**
   Hoje as entradas do caminho de resolução são duas: o nome vindo do servidor
   (validado na trava 1) e o mapa compilado (travado na trava 2). Toda opção
   abaixo acrescenta uma **terceira**: um arquivo local editável por qualquer
   coisa que rode como o usuário. Isso é aceitável — desde que o que o arquivo
   possa dizer seja limitado a *"qual das entradas compiladas"*, nunca *"qual
   executável"*. É a linha que separa a seção 4 legítima da ilegítima.

## 4. As opções

### A. Não fazer nada agora — corrigir só o comentário

Aceitar que o mapa é de build, e trocar *"configurável fica para depois"* por
uma frase que diga a verdade: **é de build de propósito, e "adicionar um app" é
uma release, não uma configuração.**

- **Invariante:** intacta. Nada muda no capabilities.
- **Custo:** uma frase de comentário.
- **O que perde:** os casos (2) e (3) da seção 1 continuam sem resposta.
- **O que ganha:** para de prometer, no código, algo que o desenho não pode
  entregar. É a mesma conclusão a que o review do mobile já chegou para o outro
  cliente ([`review-mobile-contrato-cliente.md`](review-mobile-contrato-cliente.md),
  seção 4.2.2): *"adicionar o app X ao Shogun é uma release de loja, não uma
  configuração"*.

### B. Apelidos + liga/desliga (a leitura estrita do enunciado)

Duas chaves novas no `shogun.json`:

- `appsDesabilitados: string[]` — chaves de `APPS_CURADOS` que o usuário desligou;
- `appsApelidos: Record<string, string>` — nome normalizado → **chave existente**
  de `APPS_CURADOS`.

A resolução em `abrirApp` passa a ser: `normalizar` → apelido do usuário →
`APPS_CURADOS` → `SINONIMOS` → desligado? → `spawn`. O valor de um apelido é
validado contra `Object.keys(APPS_CURADOS)`; valor desconhecido é ignorado, no
molde do `tema`.

- **Invariante:** **preservada integralmente.** `capabilities/default.json` não
  é tocado; o teste de escopo continua valendo palavra por palavra. A config só
  escolhe *qual das quatro* entradas compiladas, nunca o que elas são.
- **Custo:** baixo-médio. Duas chaves + validação em `config.ts`, a cadeia de
  resolução em `instrucoes.ts`, uma seção nova na tela de Config (lista de 4
  apps com toggle + campo de apelido), ~10 testes de vitest.
- **Resolve:** (2) e (3) da seção 1.
- **Não resolve:** (1) — o caso que motiva o item.
- **E aqui está o problema que desqualifica B como entrega isolada:** a tela de
  Config passa a ter uma seção **"Apps"**. A primeira coisa que qualquer pessoa
  faz ao abrir uma seção chamada "Apps" é procurar o botão **"adicionar"** — que
  não existe e, por desenho, não pode existir. B constrói a porta de entrada da
  expectativa (1) e a entrega trancada. Hoje não há tela nenhuma e ninguém se
  frustra; com B, a frustração ganha um lugar para acontecer.
- **Ressalva adicional sobre o valor real dos apelidos:** o apelido é casado
  contra o `app` que **o LLM extraiu**, não contra a frase do usuário. Com
  `claude`, `deepseek` ou `openai_mini`, o modelo já normaliza "abre meu player
  de música" para `Spotify` — o apelido nunca é consultado. Ele só morde quando
  o nome chega literal, que é o comportamento do
  `DeterministicoProvider` (`_PADRAO_ABRIR` pega o texto cru depois de "abre").
  Ou seja: **apelidos no cliente são, em boa parte, remendo para a literalidade
  do provedor de fallback** — e o remédio natural para isso é o prompt do
  servidor, não configuração no desktop.

### C. Catálogo de build + habilitar/apelidar (a opção que fecha o item)

O capabilities passa a declarar um **catálogo maior** de comandos nomeados —
todos com `cmd` e `args` literais, como hoje — e `APPS_CURADOS` ganha a entrada
correspondente para cada um. A configuração decide **quais do catálogo estão
ativos** e como se chamam.

Exemplos de entradas viáveis sem alargar nada, todas no molde das quatro atuais:

| comando | `cmd` | `args` |
|---|---|---|
| `abrir-discord` | `explorer.exe` | `["discord://"]` |
| `abrir-steam` | `explorer.exe` | `["steam://"]` |
| `abrir-whatsapp` | `explorer.exe` | `["whatsapp://"]` |
| `abrir-email` | `explorer.exe` | `["mailto:"]` |
| `abrir-bloco-de-notas` | `notepad.exe` | `false` |
| `abrir-terminal` | `wt.exe` | `false` |

- **Invariante:** **preservada.** Cada entrada continua sendo um comando nomeado
  com executável e args fixos em build. O usuário nunca digita nem escolhe
  executável; ele liga ou desliga o que o binário já sabe fazer. A trava 2 vale
  igual com 4 ou com 20 entradas.
- **Resolve:** (1), (2) e (3) — é a **única** opção que faz o Shogun abrir um
  app que ele não abria, sem furar o desenho.
- **Custo:** médio. O código é o mesmo de B; o que cresce é o catálogo e a
  decisão de produto por trás dele.
- **E é exatamente aí que ele para:** *quais* apps entram no catálogo é decisão
  do Marcus, não de um agente. Pior, cada entrada arrasta uma sub-decisão
  (seção 6.2): **o que acontece quando o app não está instalado?** `explorer.exe
  discord://` numa máquina sem Discord abre o diálogo do Windows *"Como você
  quer abrir isto?"* — e o `spawn` retorna sucesso, então o Shogun fala *"Pedi
  para este aparelho abrir o Discord"* enquanto a tela mostra um erro. Com 4
  entradas curadas para a máquina do Marcus isso é teórico; com um catálogo de
  20, é o caso comum.
- **Efeito no teste de escopo:** continua passando (toda entrada do catálogo tem
  chave no mapa), mas a igualdade bidirecional passa a cobrir 20 pares em vez de
  4 — o que é bom, e barato.

### D. Parametrizar o argumento (ex.: a URL do navegador)

Trocar, no capabilities, `"args": ["https://www.google.com"]` por um argumento
com **validador de regex** em vez de literal, para que o usuário escolha a
página inicial.

- **Invariante: alargada.** Hoje o argumento é *uma* string; passaria a ser
  *qualquer* string que case com o padrão. É a diferença entre "este comando faz
  isto" e "este comando faz uma família de coisas". Mesmo com um validador
  apertado (`^https://[^\s]+$`), a trava 2 deixa de ser "executável e args
  fixos" — e essa frase é a que está escrita no comentário do `instrucoes.ts`,
  no ROADMAP e no `CONTEXTO-GERAL.md`.
- **Custo colateral:** `instrucoes.escopo.test.ts` compara `args` **literalmente**
  (`expect(permissao!.args).toEqual(esperado)`). Um validador não é comparável
  por igualdade; o teste precisaria de um modo novo. Enfraquecer a única rede
  mecânica do acoplamento para ganhar uma página inicial configurável é troca
  ruim.
- **Verificação pendente:** o suporte a `{ "validator": … }` em `args` é da
  especificação de escopo do `tauri-plugin-shell` v2; não foi exercitado neste
  repositório e `src-tauri/gen/schemas/` só existe depois de um build. Ninguém
  deveria decidir isto sem antes gerar o schema e confirmar contra a versão
  instalada (`^2.3.6`).
- **Valor entregue:** a página inicial do navegador. **Desqualificada** — custo
  na invariante e na rede de teste, por um ganho cosmético.

### E. Caminho de executável ou argumento livre digitado pelo usuário

O usuário informa `C:\...\app.exe` (ou um argumento arbitrário) na tela de
Config, e o cliente executa.

**Desqualificada, e não por precaução — por impossibilidade.** Exigiria um
escopo `shell:allow-spawn` com `cmd` genérico, o que é o mesmo que remover a
trava 2. E remover a trava 2 muda a natureza da trava 1: o argumento do PR #41
("nenhuma instrução no fio é melhor que uma instrução que carrega alvo
executável") só vale porque o outro lado não sabe executar alvo arbitrário. As
duas travas se sustentam mutuamente; derrubar uma barateia a outra.

Registrada aqui para que a pergunta não precise ser feita de novo.

## 5. Comparação

| | Toca `capabilities` | Invariante | Resolve (1) app novo | Resolve (2) apelidos | Resolve (3) desligar | Teste de escopo | Custo |
|---|---|---|---|---|---|---|---|
| A. Só corrigir o comentário | não | intacta | não | não | não | intacto | **~zero** |
| B. Apelidos + liga/desliga | **não** | **intacta** | **não** | sim | sim | intacto | baixo-médio |
| C. Catálogo de build + B | sim (só adiciona) | **intacta** | **sim** | sim | sim | intacto (mais pares) | médio |
| D. Argumento com validador | sim (alarga) | **alargada** | não | não | não | **enfraquecido** | médio |
| E. Caminho livre | sim (destrói) | **destruída** | sim | — | — | sem sentido | — |

A leitura da tabela em uma frase: **B é barato e seguro mas não fecha o item; C
fecha o item e é igualmente seguro, mas a parte cara dele é uma decisão de
produto; D e E pagam na invariante.**

## 6. Sub-decisões que nenhuma opção resolve sozinha

### 6.1 O que a tela de Config promete

Uma seção "Apps" com quatro linhas e nenhum botão de adicionar comunica
"configurável" e entrega "quatro". Se B ou C entrarem, o texto da tela precisa
dizer, **na própria tela**, que a lista é do aplicativo e que apps novos entram
por atualização — do mesmo jeito que os `<small>` da tela de Config hoje
explicam quando o token é obrigatório. Interface que não explica a própria
limitação transfere a explicação para o suporte.

### 6.2 App não instalado: o `spawn` mente

`abrirApp` usa `spawn` e não `execute` **de propósito** (abrir app é
dispara-e-esquece; `explorer.exe` devolve código de saída diferente de zero
mesmo quando abre). A consequência já está registrada em
[`acao-resultado.md`](acao-resultado.md) seção 5: **nenhum cliente consegue
reportar "o app abriu"** — o teto é *"consegui pedir ao SO"*.

Com 4 entradas escolhidas para uma máquina conhecida, a diferença é teórica. Com
um catálogo (opção C), deixa de ser: entradas por URI (`discord://`,
`steam://`, `whatsapp://`) *sempre* aceitam o `spawn`, instaladas ou não. O
liga/desliga da opção B vira, na prática, o **único** mecanismo que impede o
Shogun de afirmar que abriu algo que não existe — e ele depende de o usuário
configurar corretamente.

Não há detecção de "instalado" disponível pelo escopo atual, e adicioná-la
significaria permissão nova (ler o registro, listar `shell:AppsFolder`). Isso é
feature própria, não parte desta.

### 6.3 Apelidos podem ser problema do servidor, não do cliente

Ver a ressalva da opção B. Se o caso concreto for "o Shogun não entende como eu
chamo o Spotify", vale medir **onde** a tradução falha antes de construir a
tabela no cliente: se o provedor principal já acerta, a configuração nasce
inerte e o custo real está no `SYSTEM_PROMPT`.

### 6.4 Não há dado sobre o que falha

`acao-resultado.md` (seções 1c, 5 e 8) registra que os nomes de app que caem no
`fallback_text` existem **só no `console.warn` do cliente** — o servidor nunca
fica sabendo. Aquele documento recomendou não implementar telemetria agora, e
listou como **gatilho concreto para reabrir a decisão**: *"o mapa de apps
configurável entra: quem configura precisa saber quais nomes o LLM manda e
falham"*.

Os dois documentos se apontam. É simetria honesta, não impasse: significa que
**a pergunta "quais apps o Marcus pede e não consegue abrir?" não tem resposta
medida hoje, em nenhum dos dois lados** — e é exatamente ela que decidiria o
catálogo da opção C.

## 7. Impacto no mobile

Nenhum, e isso é um dado a favor de A/B e contra apressar C.

O mobile está congelado até pós-v1.0 e **nunca lê `instruction`**
(`mobile/src/contracts.ts` → `StatusScreen.tsx`). Mais importante: o review do
contrato já concluiu que, no celular, *"configurável por schemes arbitrários
nunca vai existir"* — mudar a lista exige build **e submissão à loja**.

Consequência prática: se o desktop ganhar um catálogo de 20 apps, os dois
clientes do mesmo contrato passam a ter listas muito diferentes, e o
`fallback_text` por aparelho — que o contrato já resolve de graça — passa a ser
o caminho comum no mobile. Não quebra nada; muda a expectativa de produto, e vale
decidir o catálogo do desktop sabendo disso.

## 8. Recomendação

**Fazer a opção A agora — corrigir o comentário para parar de prometer
configurabilidade que o desenho não pode dar — e tratar a opção C como a forma
correta do item, a ser aberta quando o Marcus decidir o catálogo. Não
implementar B isoladamente.**

O raciocínio, sem rodeio:

- **O item de backlog, como está escrito, promete (1) e só pode entregar
  (2)+(3).** Entregar B e marcar "mapa de apps configurável" como feito seria
  fechar o item sem resolvê-lo — e com uma tela nova que faz a promessa não
  cumprida ficar mais visível do que está hoje.
- **C é o desenho certo e preserva a invariante inteira.** Ela não precisa de
  nenhuma permissão de tipo novo: só de mais entradas do mesmo tipo que já
  existe. O que falta em C não é engenharia — é a lista, e a lista é do Marcus.
- **B não é errado; é prematuro.** Ele vira a metade barata de C no dia em que C
  entrar, e o código é literalmente o mesmo. Construí-lo antes do catálogo é
  construir o painel de controle antes de existir o que controlar.
- **A ressalva dos apelidos (6.3) e a falta de dado (6.4) apontam para o mesmo
  lugar:** ninguém sabe hoje quais nomes de app o Marcus pede e o Shogun recusa.
  Essa é a informação que dimensiona o catálogo — e sem ela, tanto o catálogo
  quanto a tabela de apelidos são chute.
- **D e E estão tecnicamente desqualificadas** (seção 4), e ficam registradas
  para não voltarem como sugestão.

**O que fazer nesta rodada (custo ~zero):** trocar a frase *"configurável fica
para depois"* em `instrucoes.ts` por algo como *"o mapa é de build de propósito:
a trava 2 fixa executável e args por comando nomeado, então adicionar um app é
atualização, não configuração — ver `docs/mapa-apps-configuravel.md`"*.
Deliberadamente **não feito nesta branch**: aquele bloco de comentário está sendo
referenciado por outro agente nesta rodada, e a frase é de uma linha.

**Quando C entrar, a ordem é:** catálogo no capabilities + `APPS_CURADOS`
(o teste de escopo cobre) → liga/desliga (sem ele, 6.2 fica pior que hoje) →
apelidos (só se 6.3 mostrar que o servidor não resolve).

**Gatilhos para reabrir a decisão** (qualquer um basta):

- o Marcus listar os apps que quer — aí C tem o que faltava e vale a rodada;
- aparecer caso concreto e repetido de nome de app que cai no `fallback_text`
  (hoje visível só no F12);
- o Shogun sair da máquina do Marcus para uma segunda máquina — o mapa de build
  deixa de poder ser curado para um ambiente conhecido, e 6.2 vira problema real;
- a telemetria da opção B de `acao-resultado.md` entrar e produzir a lista da
  seção 6.4.

## 9. O que **não** está decidido aqui

Tudo abaixo precisa de aval antes de qualquer implementação:

1. **A decisão principal: A, B ou C.** A recomendação é **A agora, C quando
   houver catálogo** (seção 8). "Não vale ainda, corrige o comentário" é a
   conclusão honesta — mas a chamada é do Marcus.
2. **Se C: quais apps entram no catálogo.** É decisão de produto, não de
   engenharia. Cada entrada precisa de `cmd` + `args` literais que funcionem na
   máquina alvo.
3. **Se C: o que fazer com app não instalado** (seção 6.2). Aceitar que o
   `spawn` mente e confiar no liga/desliga? Ou abrir a feature separada de
   detecção, que custa permissão nova?
4. **Se B ou C: o texto da tela de Config** que explica por que não há botão de
   adicionar (seção 6.1). É decisão de produto, e é o que evita a frustração
   descrita na opção B.
5. **Apelidos são problema do cliente ou do `SYSTEM_PROMPT`?** (seção 6.3). Se a
   resposta for "do prompt", a tabela de apelidos não deve ser construída — e a
   tarefa muda de área, do desktop para o servidor.
6. **Se D voltar à mesa:** exige antes gerar `src-tauri/gen/schemas/` e
   confirmar o suporte a `{ "validator": … }` na versão instalada do
   `tauri-plugin-shell` (`^2.3.6`), **e** decidir o que fazer com a comparação
   literal de `args` em `instrucoes.escopo.test.ts`. A recomendação é não voltar.
7. **A relação com `acao-resultado.md`** (seção 6.4). Os dois documentos se
   citam como pré-requisito um do outro. Se o Marcus quiser sair do impasse pelo
   dado, a opção B daquele documento (só log, custo baixo, sem contrato nem
   migração) é o caminho mais barato — e é decisão de coordenação, porque a rota
   é do **agente-backend** e o relatório sai do **agente-desktop**.
