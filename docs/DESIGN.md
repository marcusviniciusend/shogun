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
2. [server] Se session_id == null: cria sessão e devolve o id      🟡
        │
        ▼
3. POST /comando { session_id?, texto }                            ✅
        │
        ├─ Valida token                                            ✅
        ├─ SELECT histórico da sessão                              ✅
        ├─ INSERT mensagem do usuário na sessão                    ✅
        │
        ▼
4. Servidor monta prompt com histórico + comando novo              🟡
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
8. [fim] INSERT mensagem do assistente, UPDATE da sessão           ✅
```

Resumindo: **existe hoje o miolo** (autenticação, interpretação pelo LLM,
execução da ação) **e a memória em volta dele** (passos 3 e 8, com o 4 na versão
concatenada). Falta o **lado cliente da sessão** (passo 2: guardar o id entre
execuções) e **a entrega incremental** (passos 6 e 7).

---

## 1. Cliente manda o comando transcrito — ✅ Existe

O desktop (Tauri) ou o mobile (RN) já transcreveu o áudio localmente e envia
apenas texto. O STT fica no cliente por decisão de latência — o servidor nunca
recebe áudio.

## 2. Criação da sessão — ✅ Existe (no servidor)

`CommandRequest.session_id` é `Optional[str]`. Nulo significa conversa nova.

**Decisão tomada: quem gera o id é o servidor.** Era a alternativa apontada
aqui, e resolve o ponto levantado — com o id nascendo no cliente, um cliente
pode inventar id de sessão alheia. Irrelevante com um usuário só, mas é o que
amarra o `user_id` discutido em [DATABASE.md](DATABASE.md) quando houver mais de
um, e mudar depois seria mudança de contrato.

Na primeira mensagem o cliente manda `session_id` nulo; o servidor cria a sessão
e devolve o id em `CommandResponse.session_id`. O cliente guarda e reenvia nas
próximas. Um id vindo do cliente continua sendo aceito e materializado — quem já
tem conversa não a perde.

Falta só o lado do cliente: guardar o id entre execuções.

## 3. `POST /comando` — 🟡 Parcial

### Validação do token — ✅ Existe

`require_auth` (`app/core/security.py`) é dependência do router inteiro, então
nenhuma rota de comando existe sem ela. Bearer fixo em `SHOGUN_AUTH_TOKEN`,
comparado com `secrets.compare_digest` para não vazar o token por timing. Token
vazio desliga a autenticação — só para desenvolvimento local, e o servidor avisa
no log de inicialização.

### INSERT da mensagem do usuário — ✅ Existe

Grava o texto recebido em `messages` com `role="user"`, **antes** de chamar o
modelo.

A ordem importa: gravando antes, um comando que falha no LLM continua registrado.
Se gravasse depois, toda falha do modelo apagaria a pergunta do Marcus do
histórico — e o passo 5 já pode falhar hoje (503 quando provedor e fallback caem
juntos).

Se a sessão ainda não existe no banco, é aqui que ela é criada.

### SELECT do histórico — ✅ Existe

Lê as últimas N mensagens da sessão (`SHOGUN_HISTORICO_MAX_MENSAGENS`, default
20). O índice `(session_id, id)` serve exatamente esta consulta.

A leitura acontece **antes** do INSERT da mensagem nova — senão o comando atual
apareceria duas vezes no prompt, uma no bloco de contexto e outra no fim.

## 4. Montagem do prompt com histórico — 🟡 Parcial (versão concatenada)

Cada comando era interpretado sem memória do anterior: "e as outras?" logo depois
de "quais são minhas pendências?" não tinha como funcionar. Agora tem.

**A interface não mudou.** `interpretar_comando(texto)` continua recebendo uma
string; o histórico entra concatenado nela, em
`app/core/llm/historico.py`:

```
Histórico da conversa (mais antigo primeiro):
Marcus: quais são minhas pendências?
Shogun: Você tem 2 pendências: ...

Comando atual:
e as outras?
```

Sem histórico, o prompt é o comando puro — conversa nova não carrega bloco de
contexto vazio.

Foi escolha deliberada de não mexer na assinatura: trocá-la atinge os quatro
provedores de uma vez, e ainda não se sabe se a concatenação é boa o bastante
para justificar isso. O `SYSTEM_PROMPT` segue fixo e idêntico em todos.

### Migração futura para assinatura estruturada

**Se a qualidade da versão concatenada não se sustentar**, o caminho é
`interpretar_comando` passar a receber uma lista de mensagens
(`[{"role": ..., "content": ...}]`), que é o formato nativo das APIs dos quatro
provedores. Os sinais de que chegou a hora:

- o modelo confundir quem falou o quê, ou responder ao histórico em vez do
  comando atual;
- o modelo tratar o bloco de contexto como parte do comando (ex.: repetir uma
  resposta antiga);
- o modelo local degradar mais que os de nuvem no mesmo histórico — sinal de que
  o formato em texto puro está custando atenção que a estrutura não custaria.

O custo é conhecido: os quatro provedores, `FallbackLLMProvider` e os testes de
cada um. `montar_prompt` some, e o `SYSTEM_PROMPT` continua onde está.

Uma decisão segue em aberto: o que fazer quando o histórico estourar o contexto
— truncar as mais antigas (hoje) vs. resumir. A janela é por contagem de
mensagens, não por orçamento de tokens: precisa caber no menor contexto entre os
provedores, e contar mensagem é previsível sem tokenizer.

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

## 8. INSERT do assistente e UPDATE da sessão — ✅ Existe

Fecha o ciclo: grava a resposta em `messages` com `role="assistant"` e atualiza
`sessions.updated_at`. É o que torna o SELECT do passo 3 útil na próxima
mensagem.

Com streaming, o texto gravado é o que foi montado incrementalmente — a gravação
acontece no fim do stream, não a cada pedaço.

Vale registrar junto qual provedor respondeu: sem isso não dá para saber depois
se uma resposta ruim veio do modelo local ou do fallback de nuvem.

---

## O que falta, em ordem de dependência

1. ~~**Persistência** (`sessions` + `messages`) — passos 3 e 8~~ → feito, ver [DATABASE.md](DATABASE.md)
2. ~~**Histórico no contexto** — passo 4~~ → feito na versão concatenada, sem mexer na interface `LLMProvider`
3. **Sessão no cliente** — passo 2: o servidor já devolve o id; falta o cliente guardá-lo entre execuções
4. **Assinatura estruturada do `LLMProvider`** — só se a concatenação do passo 4 não segurar; critérios no passo 4
5. **Streaming** — passos 6 e 7, depende de resolver a tensão com saída estruturada
6. **Contrato de `abrir_app`** — independente dos demais → [AGENTS.md](AGENTS.md)
