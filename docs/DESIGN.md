# Fluxo de uma mensagem

Caminho completo de um comando, do cliente até a voz de volta. **É o desenho
alvo, não o estado atual**: parte já roda, parte é plano.

| Marcador | Significado |
| --- | --- |
| ✅ **Existe** | implementado e coberto por testes hoje |
| 🟡 **Parcial** | existe, mas muda quando os passos novos entrarem |
| 🔴 **Novo** | ainda não implementado |

## O fluxo

```
1. Cliente (desktop/mobile) manda comando de voz transcrito        ✅
        │
        ▼
2. [client] Se session_id == null: cria nova sessão                🔴
        │
        ▼
3. POST /comando { session_id, texto }                             🟡
        │
        ├─ Valida token                                            ✅
        ├─ INSERT mensagem do usuário na sessão                    🔴
        ├─ SELECT histórico da sessão                              🔴
        │
        ▼
4. Servidor monta prompt com histórico + comando novo              🔴
        │
        ▼
5. Chama LLMProvider (Claude/DeepSeek/GPT-4o mini/Ollama,          ✅
   com fallback automático)
        │
        ▼
6. Stream da resposta de volta ao cliente (SSE/WebSocket)          🔴
        │
        ▼
7. Cliente toca TTS conforme os tokens chegam                      🔴
   (ou espera completar, se não streamar)
        │
        ▼
8. [fim] INSERT mensagem do assistente, UPDATE da sessão           🔴
```

Resumindo: **existe hoje o miolo** (autenticação, interpretação pelo LLM,
execução da ação); **falta a memória em volta dele** (passos 2, 3-INSERT,
3-SELECT, 4 e 8) e **a entrega incremental** (passos 6 e 7).

---

## 1. Cliente manda o comando transcrito — ✅ Existe

O desktop (Tauri) ou o mobile (RN) já transcreveu o áudio localmente e envia
apenas texto. O STT fica no cliente por decisão de latência — o servidor nunca
recebe áudio.

## 2. Criação da sessão no cliente — 🔴 Novo

Se o cliente não tem `session_id`, ele cria um antes de falar com o servidor.

Hoje `CommandRequest.session_id` é `str` obrigatório: não existe o caso
`session_id == null` que o passo prevê, e nenhum cliente cria sessão. Duas coisas
mudam aqui — o contrato em `shared/` passa a aceitar nulo, e o cliente ganha a
responsabilidade de gerar e guardar o id entre execuções.

Decisão pendente: **quem gera o id**. O contrato atual (id vindo do cliente)
implica que um cliente pode inventar id de sessão alheia — irrelevante com um
usuário só, mas é o que amarra o `user_id` discutido em
[DATABASE.md](DATABASE.md) se um dia houver mais de um. A alternativa é o
servidor devolver o id na primeira resposta.

## 3. `POST /comando` — 🟡 Parcial

### Validação do token — ✅ Existe

`require_auth` (`app/core/security.py`) é dependência do router inteiro, então
nenhuma rota de comando existe sem ela. Bearer fixo em `SHOGUN_AUTH_TOKEN`,
comparado com `secrets.compare_digest` para não vazar o token por timing. Token
vazio desliga a autenticação — só para desenvolvimento local, e o servidor avisa
no log de inicialização.

### INSERT da mensagem do usuário — 🔴 Novo

Grava o texto recebido em `messages` com `role="user"`, **antes** de chamar o
modelo.

A ordem importa: gravando antes, um comando que falha no LLM continua registrado.
Se gravasse depois, toda falha do modelo apagaria a pergunta do Marcus do
histórico — e o passo 5 já pode falhar hoje (503 quando provedor e fallback caem
juntos).

Se a sessão ainda não existe no banco, é aqui que ela é criada: o passo 2 gera o
id, o servidor materializa a linha em `sessions`.

### SELECT do histórico — 🔴 Novo

Lê as últimas N mensagens da sessão. O índice `(session_id, id)` proposto em
[DATABASE.md](DATABASE.md) serve exatamente esta consulta.

## 4. Montagem do prompt com histórico — 🔴 Novo

**É a mudança conceitual maior do plano.** Hoje `interpretar_comando(texto)`
recebe uma string solta: cada comando é interpretado sem memória do anterior, e
"e as outras?" logo depois de "quais são minhas pendências?" não tem como
funcionar. Com histórico, a interface `LLMProvider` passa a receber uma lista de
mensagens — o que afeta os quatro provedores de uma vez.

O `SYSTEM_PROMPT` continua fixo e idêntico em todos eles; o histórico entra
depois dele, antes do comando novo.

Duas decisões em aberto: **quantas** mensagens (janela fixa vs. orçamento de
tokens) e o que fazer quando estourar o contexto (truncar as mais antigas vs.
resumir). O modelo local (Hermes 3 8B) tem contexto menor que os de nuvem, então
o limite precisa caber no menor dos provedores, não no maior.

## 5. Chamada ao LLMProvider — ✅ Existe

- abstração `LLMProvider` com quatro implementações (`claude`, `deepseek`,
  `openai_mini`, `ollama`), escolhidas por `SHOGUN_LLM_PROVIDER`;
- `SYSTEM_PROMPT` e schema de saída (`acao`, `parametros`, `resposta_falada`)
  centralizados em `base.py` — idênticos em todos os provedores;
- `FallbackLLMProvider`: qualquer `LLMIndisponivelError` (timeout, rate limit,
  credencial ausente, JSON malformado, resposta fora do schema) passa o comando
  ao reserva, com o motivo no log. Se os dois falharem, a rota devolve **503**.

A interpretação despacha a ação:

| Ação | Estado |
| --- | --- |
| `conversar` | ✅ usa a `resposta_falada` do modelo, sem agente |
| `consultar_pendencias` | ✅ `PendenciasProvider` injetado, ordenado por prioridade, com `limite` opcional |
| `abrir_app` | 🟡 placeholder — quem tem acesso ao SO é o cliente; falta fechar o contrato |

Falhas do provedor de pendências viram `AgentAction(status="error")` na resposta,
nunca uma exceção — integração externa fora do ar não derruba o comando. Ver
[AGENTS.md](AGENTS.md).

## 6. Stream da resposta — 🔴 Novo

Hoje a resposta é um `CommandResponse` único, entregue quando tudo terminou; o
cliente espera em silêncio a interpretação inteira.

**Uma tensão a resolver antes de implementar:** os provedores usam saída
estruturada (JSON schema fechado), e a fala é um *campo* desse JSON. Não dá para
streamar `resposta_falada` token a token sem uma das duas saídas — (a) parsing
incremental do JSON parcial, ou (b) duas chamadas, uma que decide a ação e outra
que gera a fala em texto puro. A opção (b) dobra o custo por comando; a (a) é
mais frágil com modelo local.

Consequência do mesmo ponto: as ações de agente só existem **depois** da
interpretação completa, então o que se streama é a fala, não as `actions`.

SSE ou WebSocket: a arquitetura já prevê WebSocket para a conversa em tempo real,
e ele serve os dois sentidos; SSE é mais simples se o fluxo for só servidor →
cliente.

## 7. TTS no cliente — 🔴 Novo

O cliente sintetiza a voz conforme os tokens chegam, ou espera a resposta
completa se o streaming não estiver ligado. O passo 6 precisa entregar em
fronteiras que dêem para falar (frase ou oração), não em tokens soltos — senão o
TTS corta no meio das palavras.

Motor de TTS e onde ele roda continuam em aberto (ver
[architecture.md](architecture.md)).

## 8. INSERT do assistente e UPDATE da sessão — 🔴 Novo

Fecha o ciclo: grava a resposta em `messages` com `role="assistant"` e atualiza
`sessions.updated_at`. É o que torna o SELECT do passo 3 útil na próxima
mensagem.

Com streaming, o texto gravado é o que foi montado incrementalmente — a gravação
acontece no fim do stream, não a cada pedaço.

Vale registrar junto qual provedor respondeu: sem isso não dá para saber depois
se uma resposta ruim veio do modelo local ou do fallback de nuvem.

---

## O que falta, em ordem de dependência

1. **Persistência** (`sessions` + `messages`) — passos 3 e 8 → [DATABASE.md](DATABASE.md)
2. **Sessão no cliente** — passo 2, muda `CommandRequest` em `shared/`
3. **Histórico no contexto** — passo 4, muda a interface `LLMProvider`
4. **Streaming** — passos 6 e 7, depende de resolver a tensão com saída estruturada
5. **Contrato de `abrir_app`** — independente dos demais → [AGENTS.md](AGENTS.md)
