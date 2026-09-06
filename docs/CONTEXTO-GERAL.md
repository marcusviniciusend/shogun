# Shogun — contexto geral do projeto

> **Para que serve este documento.** Ponto único de entrada para recuperar o
> contexto do projeto em uma sessão nova — humana ou de agente — sem precisar
> reler conversas antigas. Consolida o estado do código, as decisões já tomadas
> (com a justificativa de cada uma), as decisões em aberto e as pendências
> técnicas.
>
> **Última atualização:** 2026-09-05.
>
> Este arquivo **descreve**; ele não substitui as fontes. Quando divergir do
> código, o código vence — e o documento precisa ser corrigido.

## Índice

1. [Estado atual do código](#1-estado-atual-do-código)
2. [Decisões de arquitetura tomadas](#2-decisões-de-arquitetura-tomadas)
3. [Decisões em aberto — rede e provedor padrão](#3-decisões-em-aberto--rede-e-provedor-padrão)
4. [Pendências técnicas conhecidas](#4-pendências-técnicas-conhecidas)
5. [Convenções de trabalho](#5-convenções-de-trabalho-resumo)
6. [Mapa de documentos](#6-mapa-de-documentos)

---

## 0. O que é o Shogun, em um parágrafo

Assistente pessoal de voz estilo JARVIS, para desktop e mobile. O desenho é
**um cérebro, vários clientes**: um servidor central concentra inteligência,
memória e orquestração; os clientes só capturam áudio, mostram a interface e
reproduzem a resposta. O ciclo de um comando é: cliente transcreve o áudio (STT
local) → `POST /comando` com o texto → servidor interpreta a intenção via
`LLMProvider` → despacha a ação → cliente sintetiza a resposta em voz (TTS).

---

## 1. Estado atual do código

### 1.1 Onde o código está

**Tudo está em `dev`** (`f923204`). Não há branch de feature aberta: os quatro
PRs foram mergeados e o GitHub removeu as branches remotas ao fechá-los.

| PR | Branch | O que trouxe |
|---|---|---|
| #3 | `feature/servidor-central` | `/comando`, camada de LLM, domínio, testes |
| #4 | `feature/docs-fluxo-mensagem` | `docs/DESIGN.md`, `DATABASE.md`, `AGENTS.md` |
| #5 | `feature/acesso-remoto-tailscale` | `SHOGUN_HOST`, validação do bind, CORS |
| #6 | `feature/persistencia-sqlite` | `sessions`/`messages`, Alembic, histórico no prompt |

Suíte na ponta de `dev`: **134 passed**.

`main` continua tendo só `README.md` + `LICENSE`, e segue sendo a branch default
(errada) do repositório no GitHub — ver §5.

> Esta seção substituiu um aviso, agora obsoleto, de que "quase nada do servidor
> está em `dev`" e de que os documentos de `docs/` só existiam numa branch
> separada. Ambas as coisas deixaram de valer com os merges acima.

### 1.2 `server/` — o único componente com lógica real

Python 3.11+ e FastAPI. Sem empacotamento (não há `pyproject.toml` instalável): o
`sys.path` é ajustado em `server/app/core/contracts.py` e em
`server/tests/conftest.py`.

```
server/app/
├── main.py                  # FastAPI: /health + router de comando + lifespan
├── api/comando.py           # POST /comando
├── core/
│   ├── config.py            # Settings (pydantic-settings, lê .env)
│   ├── contracts.py         # ponte para shared/python
│   ├── security.py          # autenticação Bearer
│   ├── rede.py              # descobre o bind real do uvicorn no startup
│   ├── pendencias.py        # injeção do PendenciasProvider no FastAPI
│   ├── persistencia.py      # injeção do RepositorioConversas no FastAPI
│   └── llm/                 # base, registry, fallback, claude, openai_compat,
│                            # ollama, historico (prompt com histórico)
├── db/                      # persistência — models, engine, repositorio
├── domain/                  # domínio puro — sem HTTP, sem FastAPI
│   ├── pendencias.py        # StatusAgente, Pendencia, PendenciasProvider (ABC)
│   └── providers/           # MaestriProvider (stub), ShogunOrquestradorProvider
└── agents/                  # só __init__.py e README — nenhum agente escrito
```

**Regra de dependência:** `domain/` não importa nada de `api/` nem do FastAPI. A
rota depende da **interface**, nunca de uma implementação concreta; a troca
acontece na injeção de dependência (`app.dependency_overrides` nos testes).

#### `LLMProvider` e implementações

O contrato está em `server/app/core/llm/base.py` — um `Protocol` com um método:

```python
async def interpretar_comando(self, texto: str) -> ComandoInterpretado
```

Também em `base.py`, compartilhados por **todos** os provedores:

- `SYSTEM_PROMPT` — a personalidade do Shogun. Trocar de LLM não muda quem ele é.
- `ESQUEMA_COMANDO` — JSON Schema **fechado** (`additionalProperties: false` em
  todo objeto, exigido pelo structured output da Anthropic e pelo strict mode da
  OpenAI). Saída: `{acao, parametros, resposta_falada}`. `acao` é o enum
  `conversar | consultar_pendencias | abrir_app`; `parametros` declara `app` e
  `limite` como obrigatórios e anuláveis (o modelo emite `null` explícito no que
  não se aplica) — os nulos são descartados em `parsear_comando`.
- `DICA_ESQUEMA` — o schema em linguagem natural, **acrescentado** ao
  `SYSTEM_PROMPT` nos provedores sem enforcement nativo. Nunca o substitui.
- `LLMIndisponivelError` — erro único para toda falha (rede, timeout, rate limit,
  credencial ausente, JSON malformado, resposta fora do schema). É o que a rota
  trata e o que dispara o fallback.
- `ConfiguracaoInvalidaError(ValueError)` — erro de **configuração**, não de
  disponibilidade. Estoura na construção do provedor; não cai no fallback, porque
  nenhuma retentativa resolveria.

Provedores registrados em `PROVIDERS` (`core/llm/registry.py`):

| `SHOGUN_LLM_PROVIDER` | Classe / arquivo | Saída estruturada |
|---|---|---|
| `claude` | `ClaudeProvider` (`claude.py`) | `output_config.format` — json_schema nativo |
| `deepseek` | `DeepSeekProvider` (`openai_compat.py`) | JSON mode + schema no prompt |
| `openai_mini` | `OpenAIMiniProvider` (`openai_compat.py`) | `response_format` json_schema `strict` |
| `ollama` | `OllamaProvider` (`ollama.py`) | `format` com JSON Schema completo, via `/api/chat` |

Notas do `OllamaProvider` que custaram decisão:

- Usa o endpoint **nativo** `/api/chat`, não o `/v1/chat/completions` compatível
  com OpenAI: só o nativo aceita um JSON Schema completo no campo `format` e o
  converte em gramática, restringindo a decodificação. Exige **Ollama 0.5+**.
- `OLLAMA_MODEL` é **obrigatória e sem default**. Com `ollama` selecionado e a
  variável vazia, a aplicação **não sobe** (`ConfiguracaoInvalidaError` no
  construtor) — preferível a subir e devolver 503 no primeiro comando de voz.
  Quem usa provedor de nuvem não precisa da variável.
- `configurado` é sempre `True` (modelo local não usa credencial); isso **não**
  significa "o Ollama está no ar" — a falha aparece em `interpretar_comando`.
- `temperature: 0` — interpretar comando é extração, não redação criativa.

**Fallback automático** (`core/llm/fallback.py`): `FallbackLLMProvider` envolve o
principal quando `SHOGUN_LLM_FALLBACK_PROVIDER` está preenchido. Qualquer
`LLMIndisponivelError` do principal passa o comando ao reserva, com o motivo no
log. Se os dois falharem, o erro cita os dois motivos e a rota devolve **503**.
Fallback igual ao principal é ignorado com warning. Trocar de provedor ou ligar o
fallback é **só variável de ambiente** — nenhuma rota conhece implementação
concreta.

Adicionar um provedor = uma classe implementando o `Protocol` (construtor
recebendo `Settings`) + uma entrada em `PROVIDERS`. Nada mais muda.

#### Endpoint `POST /comando`

`server/app/api/comando.py`. Recebe o texto **já transcrito** (`CommandRequest`) e
devolve `CommandResponse` (`{session_id, text, actions}`). Fluxo:

1. texto vazio → **422**;
2. `llm.interpretar_comando(texto)`; `LLMIndisponivelError` → **503**;
3. despacho por `intencao.acao`, hoje um `if/elif` na própria rota:

| Ação | Comportamento |
|---|---|
| `conversar` | devolve a `resposta_falada` do modelo, sem agente |
| `consultar_pendencias` | consulta o `PendenciasProvider` injetado, ordena por `(-prioridade, timestamp)`, aplica `limite`, monta a fala |
| `abrir_app` | **placeholder** — quem tem acesso ao SO é o cliente; falta fechar o contrato |

Duas propriedades que o código já pratica e que os agentes futuros devem manter:
**falha de integração externa nunca derruba o comando** (vira
`AgentAction(status="error")`, não exceção) e **I/O síncrono vai para a
threadpool** (`run_in_threadpool` sobre `get_pendencias_agentes`, que é síncrono
e pode fazer I/O).

Só existe `session_id` de passagem: chega no request e volta na resposta, **sem
nunca ser gravado**. Não há histórico.

#### Autenticação

`server/app/core/security.py`. Bearer token fixo em `SHOGUN_AUTH_TOKEN`,
comparado com `secrets.compare_digest` (evita vazar o token por timing).
`require_auth` é dependência do **router inteiro** — nenhuma rota de comando
existe sem ela. Token vazio **desliga** a autenticação, o que é apenas para
desenvolvimento local; o servidor avisa no log de inicialização.

#### Domínio

`Pendencia` (`agente_id`, `agente_nome`, `status`, `descricao`, `timestamp`,
`prioridade`), o enum `StatusAgente` e a ABC `PendenciasProvider` com
`get_pendencias_agentes()` e `get_status_agente(agente_id)` — ambos **síncronos e
declarados congelados** pelo agente-contratos. Implementações:
`ShogunOrquestradorProvider` (em memória, é o default da aplicação) e
`MaestriProvider` (stub — a API do Maestri ainda não existe).

#### Testes

`pytest` a partir de `server/` (`pytest.ini`, `asyncio_mode = auto`). **91
passando** em `feature/servidor-central` (`test_comando`, `test_domain`,
`test_llm`). **Nenhum teste chama API real**: provedores com cliente HTTP
mockado (`httpx.MockTransport`, para exercitar o httpx de verdade) e rotas com
`app.dependency_overrides` (`get_llm_provider`, `get_pendencias_provider`,
`get_settings`).

### 1.3 `desktop/` e `mobile/` — scaffolds funcionais

Os dois clientes existem e falam com o servidor por HTTP (`POST /comando`).
WebSocket segue como evolução futura, e ainda não existe no servidor.

| Diretório | Stack | Estado |
|---|---|---|
| `desktop/` | Tauri 2 + React (TypeScript) | **foco atual** — dashboard com chat, painel de agentes e configurações |
| `mobile/` | React Native + Expo (TypeScript) | **em backlog** — ver abaixo |

Ambos persistem o `session_id` localmente (`tauri-plugin-store` no desktop,
`AsyncStorage` no mobile) e o reenviam, então a conversa sobrevive a reaberturas.
Os tipos do fio vêm de `shared/ts`.

Captura de voz (STT) e síntese (TTS) **não existem em nenhum dos dois** — hoje a
conversa é por texto.

#### ⏸️ `mobile/` está em backlog

**Decisão do Marcus, 2026-09-05: nenhum trabalho novo em `mobile/` até o desktop
chegar a uma versão 1.0.** O scaffold está mergeado em `dev` (PR #9) e passa em
`tsc --noEmit`; fica parado onde está.

**Ao retomar, o mobile não pode ser considerado pronto sem alcançar o patamar de
resiliência do desktop** — mas o ponto de partida não é zero. Comparando
`mobile/src/api.ts` com o que o desktop recebeu em
`feature/desktop-resiliencia-basica`:

| Aspecto | Mobile hoje | Falta |
|---|---|---|
| timeout de resposta | ✅ 60 s via `AbortController`, e distingue `AbortError` | — (o **desktop** é que não tem; item 2 do levantamento) |
| erro de rede | 🟡 captura a exceção e separa timeout do resto | não registra a causa crua (sem `console.error`) e agrupa todo o resto numa frase só: porta sem ninguém escutando, DNS e rota morta ficam indistinguíveis |
| `GET /health` | 🟡 existe (`verificarSaude`) | é **manual**, só no botão "testar conexão" da aba Config. O chat e a aba Status continuam descobrindo que o servidor caiu gastando uma chamada de LLM |
| indicador de conexão | ❌ | nenhuma faixa ou badge de "servidor não alcançado" nas telas de uso |

Em resumo: o mobile já resolveu o item 2 do levantamento, que o desktop ainda
não; falta fechar os itens 1 (parcial) e 5 (a checagem existe, mas não é
automática nem visível onde importa).

`/health` custa ~1,5 ms, não exige token e não toca no modelo — descobrir por ali
que o servidor está fora é ordens de grandeza mais barato que por um
`POST /comando`, que leva de 2 a 30 s.

Referências: `.maestri/levantamento-resiliencia-desktop.md` e a branch
`feature/desktop-resiliencia-basica`. Itens 3, 4 e 6 do levantamento (retry,
modelo frio no primeiro comando, erro em duplicata) seguem abertos **nos dois** e
não são pré-requisito.

### 1.4 `shared/`

Contratos usados por servidor e clientes: `CommandRequest`, `CommandResponse`,
`AgentAction` — Pydantic em `shared/python`, TypeScript em `shared/ts`.

---

## 2. Decisões de arquitetura tomadas

### 2.1 Monorepo — um repositório, não três

**Decisão:** `server/`, `desktop/`, `mobile/` e `shared/` no mesmo repositório.

**Por quê.** O que amarra a decisão é `shared/`: os contratos
(`CommandRequest`, `CommandResponse`, `AgentAction`) são consumidos pelos três
lados ao mesmo tempo. Em repositórios separados, cada mudança de contrato viraria
publicação de pacote, versionamento e sincronização entre três PRs — para um
projeto de um desenvolvedor, é custo de coordenação sem contrapartida. No
monorepo, servidor e clientes mudam **no mesmo commit**, e um contrato quebrado
aparece na hora, não na integração.

Contexto que reforça: só um componente tem lógica hoje. Separar repositórios
agora seria pagar o custo antes de existir o que separar.

### 2.2 AGPL-3.0

**Decisão:** o projeto inteiro é AGPL-3.0 (`LICENSE`), © marcusviniciusend.

**Por quê.** É a licença copyleft que fecha a brecha de uso em rede: quem rodar
uma versão modificada do Shogun **como serviço** precisa disponibilizar o código
dessa versão. Numa arquitetura cujo componente central é justamente um servidor
acessado por rede, a GPL comum não cobriria o caso — hospedar não é distribuir. A
AGPL mantém as melhorias no ecossistema aberto sem impedir uso pessoal, estudo ou
modificação privada.

### 2.3 SQLite via SQLAlchemy para persistência

**Decisão tomada e implementada** (PR #6). O schema e as decisões estão em
`docs/DATABASE.md`, incluindo a seção "Divergências da implementação": o
`session_id` é gerado pelo **servidor** quando o cliente manda nulo, as migrações
são Alembic (e não `create_all` no startup), e os timestamps são UTC *naive* —
o SQLite devolve `datetime` sem fuso, e misturar aware com naive levanta
`TypeError` na comparação.

**Por que SQLite:**

- **Zero infraestrutura.** O banco é um arquivo; não há serviço para subir ou
  manter. Quem clona roda `uvicorn` e pronto — mesmo espírito da escolha do
  Ollama: o projeto funciona inteiro na máquina do Marcus, sem depender de nada
  externo.
- **Latência mínima.** Ler o histórico é chamada de função, não ida a outro
  processo. Num fluxo que já espera segundos pelo modelo, o banco não deve somar
  nada perceptível.
- **A carga é de um usuário falando um comando por vez.** Nenhuma vantagem de um
  banco de rede é exercida hoje.

**Por que SQLAlchemy:** sem ORM, a escolha acima seria cara de reverter — SQL à
mão espalha dialeto pelo código e trocar de banco viraria revisão de cada query.
É a mesma estratégia de `LLMProvider` e `PendenciasProvider`: **a decisão
concreta fica atrás de uma interface, e trocá-la não reescreve quem a usa.** O
acesso ao banco também deve ficar atrás de um repositório — as rotas pedem "o
histórico desta sessão", não montam query.

**Schema desenhado** (duas tabelas; só entra campo que algum passo do fluxo
precisa): `sessions` (`id` = o `session_id` do cliente, `created_at`,
`updated_at`) e `messages` (`id` autoincrement — **a ordenação canônica**,
`session_id` FK, `role`, `content`, `created_at`), com índice em
`(session_id, id)`. A ordenação é por `id` e não por `created_at` porque duas
mensagens no mesmo instante não teriam desempate, e a ordem user → assistant
precisa ser estável.

**Critérios de migração para Postgres** (já documentados; nenhum vale hoje —
qualquer um justifica reabrir a decisão):

1. deploy em servidor remoto acessível externamente;
2. múltiplos usuários simultâneos;
3. necessidade de concorrência real (`database is locked` em log, ou mais de um
   worker escrevendo);
4. volume comprometendo a performance;
5. de natureza diferente: **busca semântica no histórico** — `pgvector` decide
   sozinho, e migrar por esse motivo evita trocar de banco duas vezes.

O gatilho **1 é diretamente afetado pela decisão de rede da seção 3**: hospedar o
servidor em VPS (opção A) aciona esse critério de imediato; manter local com
túnel (opção B) não.

Cuidados de portabilidade a manter desde o primeiro dia — o ORM não os resolve
sozinho: nada de SQL cru, nada de tipos de dialeto (`sqlite.JSON`,
`postgresql.JSONB`), `Integer, primary_key=True` em vez de autoincrement
específico, **timestamps sempre em UTC** (único item que, ignorado, corrompe
dados já gravados) e **Alembic junto com o schema inicial**, não depois.

### 2.4 `LLMProvider` com múltiplos backends e fallback automático

**Decisão:** a interpretação de comandos fica atrás de uma interface de um método
só, com quatro implementações registradas em um dicionário e fallback automático
configurável por variável de ambiente.

**Por quê:**

- **Nenhum provedor é uma aposta.** Custo, disponibilidade e qualidade de
  structured output mudam depressa entre Claude, DeepSeek, GPT e modelos locais.
  Com a interface, trocar é `SHOGUN_LLM_PROVIDER=<nome>` — nenhuma rota conhece
  implementação concreta.
- **A identidade do Shogun não pode depender do fornecedor.** Por isso
  `SYSTEM_PROMPT` e `ESQUEMA_COMANDO` vivem em `base.py`, compartilhados. Um
  provedor pode variar em *como* impõe o schema, nunca em *quem o Shogun é*.
- **Um erro único torna o fallback possível.** Toda falha vira
  `LLMIndisponivelError`; sem essa normalização, o `FallbackLLMProvider` teria de
  conhecer as exceções de cada SDK.
- **Modelo local é objetivo, não curiosidade.** O `OllamaProvider` permite operar
  sem custo de API e sem mandar comandos pessoais para fora da máquina; o
  provedor de nuvem no fallback é a rede de segurança para quando o modelo 8B
  devolve JSON que não passa na validação. É o par
  `SHOGUN_LLM_PROVIDER=ollama` + `SHOGUN_LLM_FALLBACK_PROVIDER=deepseek`.
- **Fallback vale a métrica, além da resiliência.** A frequência com que o
  fallback é acionado é justamente como avaliar um modelo local candidato: cada
  acionamento é um JSON fora do schema.

---

## 3. Decisões em aberto — rede e provedor padrão

> §3.1 foi **decidida e implementada** (PR #5). §3.2 e §3.3 continuam em aberto:
> são registro do que foi discutido, para que a próxima sessão não redescubra o
> problema do zero — não tratar como fato consumado.

### 3.1 Como o mobile alcança o servidor — **decidido: Tailscale**

**O problema.** A arquitetura prevê desktop e mobile falando com um servidor
central único. Hoje o servidor roda **local, na máquina do Marcus**
(`uvicorn`, `localhost:8000`). O desktop funciona assim porque roda na mesma
máquina; **o mobile não** — fora da rede local, não há como chegar ao servidor. É
um bloqueio de arquitetura para o cliente mobile, não um detalhe de deploy.

**Opção A — hospedar o servidor inteiro numa VPS**

- A favor: sempre acessível, de qualquer rede, sem depender do PC do Marcus estar
  ligado. É o cenário "servidor de verdade".
- Contra: **complica o Ollama local.** O modelo local depende da GPU da máquina
  do Marcus; numa VPS ou não há GPU, ou ela custa caro. Na prática, empurra o
  Shogun de volta para provedores de nuvem pagos. Soma-se o **custo recorrente**
  da própria VPS.
- Efeito colateral registrado: aciona o **gatilho 1 de migração para Postgres**
  (§2.3) — servidor remoto acessível externamente traz junto backup, retenção e
  controle de acesso, que um arquivo SQLite não resolve sozinho.

**Opção B — servidor local + VPN/túnel (ex.: Tailscale)**

- A favor: o servidor continua na máquina do Marcus, então **o Ollama continua
  funcionando com a GPU local**; **sem custo de VPS**; o mobile acessa de
  qualquer rede como se estivesse na LAN. Preserva as premissas de §2.3 (banco
  local) e §2.4 (modelo local).
- Contra: **só funciona com o PC ligado.** Assistente indisponível quando a
  máquina está desligada ou dormindo.

**Decidido: opção B (Tailscale)** — e implementada no PR #5. Preserva o Ollama
com a GPU local e não gera custo recorrente. Ver "Acesso remoto via Tailscale"
no `server/README.md`.

O risco que a seção apontava — expor o servidor sem token — foi fechado no
código: o servidor **recusa subir** (erro fatal, antes de a porta abrir) quando o
bind aceita conexões de outras máquinas e `SHOGUN_AUTH_TOKEN` está vazio. Em bind
local o token continua opcional. A checagem lê o host que o **uvicorn** recebeu,
não a variável `SHOGUN_HOST`, então `uvicorn --host 0.0.0.0` também é barrado.

Continuam em aberto, agora do lado do cliente:

- como o mobile descobre/configura o endereço do servidor;
- comportamento quando o servidor está inalcançável (PC desligado).

### 3.2 OpenCode Zen como provedor padrão — **em aberto e condicionada**

Levantada a intenção de adicionar o **OpenCode Zen** como um provedor de LLM
adicional, para ser o **provedor padrão**, com os demais (Ollama, Claude,
DeepSeek, OpenAI-mini) como fallback.

**Estado: não decidido, nada implementado.** Depende de detalhes técnicos ainda
não confirmados — **API key** e **formato do endpoint** (se for compatível com a
API da OpenAI, provavelmente reaproveita o padrão de `openai_compat.py`; se não,
é uma classe própria, como o `OllamaProvider`).

**Condicionada à decisão de §3.1**, porque a arquitetura de rede influencia onde
e como esse provedor seria chamado — e a relação com o Ollama local é exatamente
o ponto em disputa: um provedor de nuvem como padrão faz mais sentido no cenário
VPS (onde o Ollama fica inviável) do que no cenário Tailscale (onde o modelo
local é justamente a razão de o servidor ficar na máquina do Marcus).

Quando for decidida, o custo de implementação é baixo por construção (§2.4): uma
classe implementando `LLMProvider`, uma entrada em `PROVIDERS`, e as variáveis no
`.env.example`. Nenhuma rota muda.

### 3.3 Outras decisões em aberto já registradas

De `docs/architecture.md` e `docs/DESIGN.md`:

- **STT**: hoje no cliente (decisão de latência); o servidor nunca recebe áudio.
- **TTS**: motor e onde roda — em aberto.
- **Quem gera o `session_id`**: hoje o cliente (e `CommandRequest.session_id` é
  `str` obrigatório, sem o caso nulo que o fluxo prevê). A alternativa é o
  servidor devolver o id na primeira resposta.
- **Janela de histórico**: quantas mensagens (contagem fixa vs. orçamento de
  tokens) e o que fazer ao estourar o contexto (truncar vs. resumir). O limite
  precisa caber no **menor** dos provedores — o modelo local tem contexto menor
  que os de nuvem.
- **Contrato de `abrir_app`**: o servidor pode rodar em outra máquina e não tem
  acesso ao SO do Marcus; ele deve devolver a instrução e o cliente executa.
  Falta o contrato, não a implementação. (A decisão de §3.1 torna isso mais
  concreto, não menos.)

---

## 4. Pendências técnicas conhecidas

| # | Pendência | Estado | Referência |
|---|---|---|---|
| 1 | **Clientes `desktop/` e `mobile/`** | só READMEs — é o maior bloco em aberto | §1.3 |
| 2 | **Escolha do modelo do Ollama** | candidatos documentados; **nenhum baixado ou testado** | `server/README.md` §"Modelos candidatos" |
| 3 | **Streaming da resposta** | não implementado; há uma tensão de desenho a resolver antes | `docs/DESIGN.md` passo 6 |
| 4 | **Sessão no lado do cliente** | o servidor já devolve o `session_id`; falta o cliente guardá-lo entre execuções | `docs/DESIGN.md` passo 2 |
| 5 | **Sem CI** | a suíte só roda quando alguém lembra | — |

### 4.1 Achados de review ainda em aberto

O PR #3 foi mergeado; o que sobrou dele é a lista do review de contrato
(`.maestri/review-contrato-consumidor.md`), que na época foi classificada como
"mergear primeiro, corrigir depois":

- ✅ **`timestamp` naive vs aware quebrando o sort** — resolvido no PR #6:
  `agora_utc()` grava UTC sem `tzinfo`, um formato interno só;
- ✅ **provider default afirmando "zero pendências" quando a fonte nunca foi
  conectada** — a rota hoje distingue os dois casos;
- ⬜ **`str(exc)` vazando detalhe de implementação para o cliente** na falha do
  provedor de pendências;
- ⬜ **`ShogunOrquestradorProvider` não é thread-safe** enquanto a rota o chama
  em threadpool. Hoje é estado em memória; some quando ele ganhar o repositório
  de verdade (§2.3 agora tem banco para apoiá-lo).

### 4.2 Modelo do Ollama

O Ollama **v0.33.3 está instalado** na máquina e serve em `localhost:11434`, mas
**nenhum modelo foi baixado** (`ollama pull` pendente) e o `OllamaProvider`
**nunca foi exercitado contra um Ollama real** — só contra fakes nos testes. Vale
um smoke test manual antes do merge.

Com `OLLAMA_MODEL` agora obrigatória, o servidor **não sobe** com o provedor
`ollama` selecionado enquanto a variável não estiver no `.env`.

Candidatos comparados em `server/README.md` (VRAM em Q4_K_M, sem contar contexto
— reserve ~1 GB a mais): `qwen2.5:7b-instruct`, `llama3.1:8b`, `hermes3:8b`,
`mistral:7b-instruct`, `mistral-nemo:12b`, `qwen2.5:14b-instruct`, `phi4:14b`,
`gemma2:9b`. O critério não é qualidade geral do modelo — o papel é estreito
(**interpretador de comando**): acertar o `ESQUEMA_COMANDO` fechado e não
degradar sob decodificação restrita. A gramática garante a **forma**, não a
**semântica**. Regra prática de avaliação: rodar **com fallback ligado** e medir
a frequência com que ele é acionado. Trocar de modelo é só `OLLAMA_MODEL`.

*Nota de contexto de máquina: a GPU disponível é uma RTX 4050 Laptop com 6 GB de
VRAM — o que coloca os candidatos de 12–14 B (`mistral-nemo:12b`,
`qwen2.5:14b-instruct`, `phi4:14b`) fora de alcance sem offload para CPU.*

### 4.3 Streaming

Hoje a resposta é um `CommandResponse` único, entregue quando tudo terminou. A
tensão a resolver **antes** de implementar: os provedores usam saída estruturada
(JSON schema fechado) e a fala é um *campo* desse JSON. Não dá para streamar
`resposta_falada` token a token sem uma de duas saídas — (a) parsing incremental
do JSON parcial, ou (b) duas chamadas, uma que decide a ação e outra que gera a
fala em texto puro. (b) dobra o custo por comando; (a) é mais frágil com modelo
local. Consequência: o que se streama é a **fala**, não as `actions` — elas só
existem depois da interpretação completa. E o transporte precisa entregar em
fronteiras faláveis (frase/oração), senão o TTS corta no meio das palavras.
SSE ou WebSocket ainda em aberto.

### 4.4 Histórico de conversa — implementado (versão concatenada)

Feito no PR #6. A rota lê as últimas `SHOGUN_HISTORICO_MAX_MENSAGENS` (default
20) mensagens da sessão e as concatena ao prompt como bloco de contexto.

**A interface `LLMProvider` não mudou.** `interpretar_comando(texto)` continua
recebendo uma string: trocar a assinatura atinge os quatro provedores de uma vez,
e ainda não se sabe se a concatenação é boa o bastante para justificar isso. Os
critérios para migrar para uma lista de mensagens estão no passo 4 do
`docs/DESIGN.md` — em resumo, o modelo confundir quem falou o quê, responder ao
histórico em vez do comando, ou o modelo local degradar mais que os de nuvem.

Duas ordens deliberadas na rota, que valem lembrar antes de mexer nela:

- o histórico é lido **antes** do INSERT da mensagem nova, senão o comando atual
  apareceria duas vezes no prompt;
- o INSERT do usuário acontece **antes** de chamar o modelo: gravando antes, um
  comando que falha no LLM continua registrado — e esse passo pode falhar (503
  quando provedor e fallback caem juntos).

### 4.5 Outras lacunas de estado

- **`agents/`**: pasta com `__init__.py` e um README de três linhas. Nenhum
  agente escrito; o roteamento é um `if/elif` na rota — adequado para três ações,
  deixa de ser com dez. O contrato sugerido (`Protocol` `Agente` com
  `executar(intencao) -> ResultadoAgente`, registrado em dicionário) está em
  `docs/AGENTS.md`. Um agente novo não é só uma classe: é também uma entrada no
  enum `ACOES`, senão o modelo nunca escolherá aquela ação.
- **WebSocket**: previsto na arquitetura e nos READMEs dos clientes; o servidor
  só tem HTTP.
- **`MaestriProvider`** é stub — a API do Maestri ainda não existe.
- **Nenhum produtor de pendências no processo**: `ShogunOrquestradorProvider` é
  em memória e nada chama `registrar_pendencia`.

---

## 5. Convenções de trabalho (resumo)

> Resumo de referência rápida. **A fonte é o `CLAUDE.md` na raiz** — em caso de
> divergência, vale ele.

**Branches**

- A branch de trabalho é sempre **`dev`**. Nunca commitar direto em `main`.
- Trabalho novo sai de `dev`, em `feature/<assunto>`.
- `main` é integrada só via PR revisado.
- ⚠️ A branch default do GitHub está como `main` — **todo PR nasce apontando para
  `main` e a base precisa ser trocada à mão para `dev`**. Conferir isso é parte
  da abertura do PR.

**Worktree isolado por agente**

O working tree principal (`C:/dev/shogun`) é compartilhado por vários agentes, e
isso já produziu um commit na branch errada e um cherry-pick duplicado. **Cada
agente deve trabalhar em worktree isolado** (`git worktree add`), não no checkout
principal.

**Commits**

- Conventional commits, em português, **sem acentos** na mensagem:
  `feat(server):`, `fix(server):`, `docs(server):`, `test(server):`,
  `chore(repo):`.
- **Um commit por escopo** — não misturar código, teste e documentação.
- Cada commit **funcional isoladamente**: a suíte passa em qualquer ponto do
  histórico, não só no fim da série.

**Testes**

`pytest` a partir de `server/`. **Nenhum teste chama API real.** Rodar a **suíte
completa** antes de considerar qualquer tarefa concluída — não só o arquivo que
você mexeu.

```bash
cd server && pip install -r requirements-dev.txt && pytest
```

**Fluxo**

1. branch a partir de `dev`; 2. implementar; 3. suíte completa verde;
4. commits atômicos; 5. `git push -u origin feature/<assunto>`;
6. **parar aqui — NÃO abrir PR automaticamente.**

O PR é aberto manualmente pelo humano. **Revisão humana é obrigatória antes de
qualquer merge — nenhum agente faz merge.**

**Onde colocar código novo**

| O quê | Onde |
|---|---|
| Contratos e interfaces de domínio | `server/app/domain/` (Pydantic/ABC, sem FastAPI, sem HTTP) |
| Implementações de `PendenciasProvider` | `server/app/domain/providers/` |
| Novo provedor de LLM | `server/app/core/llm/` + entrada em `PROVIDERS` |
| Rotas e configuração | `server/app/api/`, `server/app/core/` |
| Contrato usado também pelos clientes | `shared/` |

**Aviso de nomenclatura:** "agente" tem dois sentidos aqui e eles não se
relacionam — os **agentes do Shogun** (`server/app/agents/`, módulos do produto,
rodam em produção) e os **agentes do Maestri** (instâncias de Claude Code
escrevendo o produto, vivem fora do repositório). A ação `consultar_pendencias`
consulta pendências **dos agentes do Maestri**, via `PendenciasProvider`. Ver
`docs/AGENTS.md`.

---

## 6. Mapa de documentos

| Documento | Onde vive | Conteúdo |
|---|---|---|
| `README.md` | todas as branches | visão geral, estrutura do monorepo, como rodar |
| `CLAUDE.md` | raiz | contexto e convenções para agentes — **fonte das regras** |
| `docs/architecture.md` | `dev` | componentes, fluxo de comando, decisões em aberto |
| `docs/DESIGN.md` | `dev` | fluxo de uma mensagem, passo a passo, marcado ✅/🟡/🔴 |
| `docs/DATABASE.md` | `dev` | SQLite+SQLAlchemy, schema, divergências, migração para Postgres |
| `docs/AGENTS.md` | `dev` | os dois sentidos de "agente", contrato sugerido, agentes previstos |
| `server/README.md` | `dev` | endpoints, env vars, provedores, Ollama, banco, acesso remoto |
| `anim/README.md` | `dev` | projeto Remotion do kanji 将軍: composições por tema, flags de render e atribuição do KanjiVG |
| `.maestri/*.md` | não versionado | estado das branches, rascunhos de PR, reviews, conflitos resolvidos |
| `docs/ROADMAP.md` | `dev` | planejamento por fases: v1.0 do desktop, backlog do mobile, ideias futuras |
| **`docs/CONTEXTO-GERAL.md`** | este arquivo | consolidação de tudo acima |
