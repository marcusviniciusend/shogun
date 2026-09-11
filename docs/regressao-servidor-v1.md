# Regressão da v1.0 — metade servidor, executada

**Data:** 2026-09-11 · **Base:** `dev` @ `de273b9` · **Executor:** agente-backend

Registro da **primeira execução real** do `docs/roteiro-regressao-v1.md`. O
roteiro foi escrito e mergeado na v1.0 e, até aqui, nunca tinha sido rodado por
ninguém — a suíte de 240 testes cobre o servidor inteiro, mas só com
`TestClient`, provedor mockado e SQLite **em memória**. Nada disso exercita
processo de verdade: `uvicorn` subindo, Alembic num arquivo, rate limit
acumulando estado entre requisições, encoding atravessando o disco.

Isto aqui é o que sobra quando se tira o `TestClient` do caminho.

O que **não** está aqui: tudo que precisa de tela, áudio ou spawn de aplicativo
(F1, F3, F7 do lado cliente, F8 inteiro e F9 do painel). Esses continuam
pendentes de um humano, como o roteiro já dizia.

## Como foi executado

```
SHOGUN_DATABASE_URL=sqlite:///<arquivo descartável fora do repo>
SHOGUN_LLM_PROVIDER=deterministico      # sem credencial, sem rede
SHOGUN_AUTH_TOKEN=<token de teste>
SHOGUN_HOST=127.0.0.1                   # uvicorn na 8123
```

Banco isolado do começo ao fim: o `server/shogun.db` do Marcus foi conferido
por hash antes e depois da rodada e ficou **byte a byte idêntico**. Os limites
de rate limit ficaram nos **defaults** (20/min e 120/min) — o objetivo era ver
o número real, não um número fácil de estourar.

---

## Resultado por item

Legenda: ✅ conforme o esperado · ⚠️ funciona, mas com ressalva registrada
abaixo · 🔴 achado.

| Item | O que foi exercitado | Resultado |
|---|---|---|
| **0.1** | `alembic upgrade head` em banco zerado | ✅ três revisões aplicadas até `b8d42a6c91e0`; schema com `sessions`, `messages`, `messages_uso`, `agentes`, `pendencias` |
| **0.1 (negativo)** | subir com migração pendente | ✅ **recusa subir**, exit code **3**, mensagem nomeando a revisão esperada e o comando a rodar — ⚠️ ver A |
| **0.1 (repetido)** | subir com o banco já na head | ✅ sobe limpo |
| **0.3** | semear pendências (adaptado do `semear.py`) | ✅ funciona com o servidor **no ar** — SQLite não travou |
| **Health** | `GET /health` sem token | ✅ 200 `{"status":"ok"}` |
| **Auth** | sem token / token errado / esquema `Basic` | ✅ 401 nos três, `WWW-Authenticate: Bearer`, mensagens distintas para ausente × inválido |
| **F2.1** | `POST /comando` "bom dia" | ✅ 200, resposta do modo determinístico, sessão aberta |
| **F2.2** | "quais sao as pendencias dos agentes" | ✅ lista as duas pendências semeadas; `AgentAction` com `detail: "2 pendências"` |
| **F2.3** | texto vazio, só espaços, campo ausente | ✅ 422 `"Comando vazio."` nos dois primeiros; 422 de validação do Pydantic no terceiro. **Nenhuma sessão criada** |
| **F4** | balde `/comando` | ✅ **exatamente 20** passam, a 21ª é 429 com `Retry-After` |
| **F4** | balde de leitura | ✅ **exatamente 120** passam, a 121ª é 429 |
| **F4** | `Retry-After` no fio | ✅ presente e **real** — decai com a janela (60 → 30 → 25 → 15 em observações sucessivas), não é constante |
| **F4** | independência dos baldes | ✅ `/health` fora dos dois; `/comando` e leitura contam separado |
| **F4** | ordem auth × limite | ✅ token inválido dá **401 mesmo com o balde cheio** — não consome cota, como a docstring promete |
| **F5** | `session_id: null` → id devolvido → 2º comando no mesmo id | ✅ |
| **F6** | `GET /sessoes` | ✅ mais recente no topo, título = primeira fala do usuário, `total_mensagens` correto |
| **F6** | `GET /sessoes/{id}/mensagens` | ✅ ordem cronológica, autor `usuario`/`shogun` |
| **F6** | sessão inexistente | ✅ 404 `"Sessao 'x' nao existe."` |
| **F6.3** | formato de data no fio | ✅ **bate com o `docs/DATABASE.md`** — ver abaixo |
| **F7.1** | "abre a calculadora" | ✅ `ClientInstruction` completa na `AgentAction`; servidor **não executa nada** |
| **F7.4** | "abre o photoshop" | ✅ `fallback_text` presente — ⚠️ ver B · 🔴 ver Achado 1 |
| **F7 (PR #41)** | app com `:`, `/`, `\` | ✅ recusado nos quatro testes, e **o nome recusado não ecoa** na fala nem no `detail` |
| **F9** | `GET /consumo` | ✅ responde — 🔴 ver Achado 2 |
| — | rota inexistente | ✅ 404 |
| — | CORS desligado por default | ✅ nenhum `Access-Control-Allow-Origin` |
| — | bind exposto sem token | ✅ **recusa subir**, exit 3, mensagem citando o bind e a origem dele |
| — | bind exposto com token | ✅ sobe |
| — | `SHOGUN_CHECAR_MIGRACOES=0` | ✅ sobe — ⚠️ ver C |
| — | encoding ponta a ponta | ✅ ver abaixo |

### Formato de data — confirmado, o doc não mente

O `docs/DATABASE.md` promete duas coisas diferentes, e as duas se confirmaram
no fio:

```
GET /pendencias   → "timestamp":  "2026-09-11T23:21:41.796325Z"   ← COM Z
GET /sessoes      → "criada_em":  "2026-09-11T23:22:02.167426"    ← SEM sufixo
GET /sessoes/…/mensagens → "criada_em": "2026-09-11T23:22:02.175225"  ← SEM sufixo
```

E os valores são **UTC de verdade**: o relógio local da máquina marcava
20:22 (UTC−3) quando a API devolveu 23:22. Isso sustenta a premissa do F6.3 —
o cliente acrescentar o `Z` antes de converter para hora local está correto, e
não há erro de 3h escondido.

### Encoding — atravessa tudo intacto

Testado com acentos, travessão, CJK e emoji (`pendências — açúcar, 将軍, 🗾`),
indo por HTTP, gravando em **SQLite em arquivo no Windows** e voltando:

- a resposta sai em UTF-8 cru no corpo (`\xc3\xaa`), não em escapes `\uXXXX`;
- o texto relido pela API é **idêntico** ao enviado;
- lido direto do arquivo `.db` com `sqlite3`, também idêntico.

Nenhum problema de codepage — que é exatamente o tipo de coisa que teste com
banco em memória não pegaria.

---

## Achados

### 🔴 1. O texto otimista do `abrir_app`, agora **observado** em runtime

Este achado já existia em `.maestri/achados-rodada-9.md` (item 1), mas como
**leitura de código**. A execução real fecha a diferença: passou a ser
comportamento observado.

Sequência real, contra o servidor de verdade:

```
POST /comando  "abre o photoshop"
  text          = "Pedi para este aparelho abrir o photoshop, Marcus."
  fallback_text = "Não consegui abrir o photoshop neste aparelho, Marcus."
```

Com `photoshop` fora do `APPS_CURADOS`, o desktop mostra e fala o
`fallback_text`. Mas o que ficou gravado e o que a API devolve de volta é:

```
GET /sessoes/{id}/mensagens
  [usuario] abre o photoshop
  [shogun ] Pedi para este aparelho abrir o photoshop, Marcus.   ← ninguém ouviu isso
```

**A consequência de segunda ordem também foi confirmada.** `montar_prompt()`
transforma esse histórico no contexto do turno seguinte. Este é o prompt
literal que o próximo comando carrega:

```
Histórico da conversa (mais antigo primeiro):
Marcus: abre o photoshop
Shogun: Pedi para este aparelho abrir o photoshop, Marcus.

Comando atual:
nao abriu nao
```

O modelo recebe, como fato, que o app foi aberto — no exato momento em que o
usuário está dizendo que não foi. **Não corrigido**: a correção depende de
decisão do Marcus sobre `messages` deixar de ser append-only.

### 🔴 2. O provedor que o próprio roteiro manda usar torna o F9 incapaz de falhar

Depois de **31 sessões e 64 mensagens** reais nesta rodada:

```
GET /consumo → total_input_tokens: 0, custo_real_usd: 0.0, por_provider: []
sqlite:  messages = 64  |  messages_uso = 0
```

Está **correto**: o `deterministico` não chama API nenhuma, logo não grava
`UsoTokens`, logo não aparece em `messages_uso`. Mas o Preparo 0.1 do roteiro
manda rodar a regressão inteira com `SHOGUN_LLM_PROVIDER=deterministico` — e o
roteiro não avisa disso em lugar nenhum.

Efeito prático: quem seguir o roteiro à risca vê `/consumo` zerado e **não tem
como distinguir "funcionando" de "quebrado"**. O F9 passa por vacuidade. Para
exercitar `/consumo` de verdade é preciso um provedor que registre uso
(`ollama` local, ou semear `messages_uso` à mão).

Não é bug de código — é **lacuna do roteiro**.

---

## Ressalvas menores

### ⚠️ A. A mensagem boa da recusa de migração fica soterrada

A checagem do PR #28 funciona e a mensagem é exemplar: nomeia o banco, a
revisão esperada, o comando a rodar e a escotilha. Só que, por ser levantada
como exceção dentro do lifespan, ela sai seguida de **~35 linhas de traceback**
de `starlette`/`fastapi`/`contextlib`. O operador lê o terminal de baixo para
cima e encontra primeiro o traceback de framework; a frase útil ficou lá em
cima. O exit code (3) está correto, então supervisor nenhum se confunde — é só
ergonomia de terminal.

Efeito colateral inofensivo: a tentativa frustrada deixa um arquivo `.db` de
**0 byte** para trás (o SQLite cria no connect).

### ⚠️ B. O servidor não sabe — e não pode saber — se o app é suportado

`"abre a calculadora"` e `"abre o photoshop"` produzem respostas
**estruturalmente idênticas**: mesma `instruction`, mesmo `status: "ok"`, ambas
com `fallback_text`. Quem decide é o cliente, consultando o `APPS_CURADOS`
dele. Isso é o contrato funcionando como desenhado (o servidor pode rodar em
outra máquina), mas vale registrar explicitamente: **o F7.4 não tem metade
servidor** — do lado de cá, sucesso e falha são a mesma resposta. É também a
raiz do Achado 1.

### ⚠️ C. A escotilha `SHOGUN_CHECAR_MIGRACOES=0` custa o que o guard-rail dizia

Rodando de propósito com banco não migrado e a checagem desligada, para ver o
cenário que a checagem existe para evitar:

```
GET  /health       → 200  {"status":"ok"}      ← o indicador de conexão fica VERDE
GET  /pendencias   → 503  {"detail":"Nao consegui consultar as pendencias agora."}
GET  /sessoes      → 500  Internal Server Error
GET  /consumo      → 500  Internal Server Error
POST /comando      → 500  Internal Server Error
```

Confirma a justificativa do PR #28 ao pé da letra. Duas observações de fio:

1. `/health` responde **ok** enquanto todo o resto está quebrado. Ele não toca
   o banco, então o desktop mostraria tudo verde e falharia em cada ação.
2. A degradação é **assimétrica**: `/pendencias` tem tratamento e vira um 503
   educado; as outras três vazam 500 cru. Como a taxonomia de erro do desktop
   trata 503 como `llm_indisponivel` (o único caso de reenvio automático), um
   banco quebrado faria o cliente **reenviar `/pendencias` sozinho** e não as
   demais. Só se alcança pela escotilha ou por banco corrompido — não é
   urgente, mas é inconsistência real.

---

## O que isto muda no roteiro

O `docs/roteiro-regressao-v1.md` continua válido. O que esta rodada acrescenta:

- toda a coluna "metade servidor" dos itens F2, F4, F5, F6, F7 e F9 está
  **verificada em processo real** — não precisa mais de humano;
- o Preparo 0.1 merece uma nota sobre o F9 (Achado 2);
- o que sobra para o humano é o que sempre foi: tela, voz e app abrindo.

## O que não foi feito, de propósito

- **Nenhum bug foi corrigido.** Os dois achados estão reportados, não tocados.
- **Nenhum teste novo entrou no CI.** Tudo aqui precisa de processo e porta —
  deixaria de ser teste unitário, e o `CLAUDE.md` é explícito. Onde esse tipo
  de teste viveria (suíte de fumaça separada? job manual?) é decisão que
  ninguém tomou; fica como proposta, não como fato consumado.
