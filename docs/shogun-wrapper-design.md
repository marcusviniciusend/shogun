# shogun-wrapper e streaming SSE — opções, trade-offs e recomendação

> Documento de estudo, escrito **antes** de qualquer implementação — nenhuma
> linha de código, contrato ou rota muda aqui. Continua a análise de
> [streaming-design.md](streaming-design.md) (que decidiu: v1.0 sem streaming,
> opção (c) — streaming do campo final — como desenho para quando entrar) e
> responde duas perguntas novas: **(1)** a camada de LLM (`server/app/core/llm/`)
> deve virar um serviço HTTP separado, um "shogun-wrapper"? **(2)** que formato
> de eventos SSE o streaming deve usar quando for implementado?
> A recomendação explícita está na seção 6; o que exige aval humano, na seção 7.

## 1. O buraco

O [streaming-design.md](streaming-design.md) resolveu a tensão de fundo (schema
JSON fechado × entrega incremental) e escolheu o mecanismo — o scanner
incremental do campo final. O que ele **não** fixou foi o **transporte e o
contrato no fio**: qual endpoint, quais eventos, o que cada evento carrega, o
que o cliente pode assumir quando o provedor não streama. Sem isso, as ~3
branches estimadas para a opção (c) não têm um alvo de contrato para mirar.

Há um padrão de mercado que responde exatamente essa pergunta: um **serviço de
gateway de LLM** — um processo HTTP fino na frente do motor de inteligência,
expondo um endpoint de chat que responde `text/event-stream` com um vocabulário
pequeno de eventos tipados:

| Evento | Papel |
| --- | --- |
| `status` | progresso legível ("consultando a base…"), emitido no início de cada etapa interna |
| `chunk` | fragmento de texto da resposta, conforme é gerado |
| `final` | a resposta completa e limpa, sempre emitida ao fim — mesmo para quem ignorou os chunks |
| `done` | terminador do stream, carregando o uso de tokens; **sempre emitido**, inclusive em timeout e erro |

Duas propriedades desse vocabulário valem mais que o resto e são o motivo de
estudá-lo: **`final` é autoritativo e `chunk` é melhor-esforço** — um cliente
que não quer (ou não sabe) streamar consome só o `final` e funciona igual; e
**`done` sempre chega**, então o cliente distingue "stream terminou" de
"conexão caiu no meio".

A pergunta (1) — separar a camada de LLM num processo próprio — vem junto
porque é assim que esse padrão costuma ser implantado: o gateway como serviço
independente do backend principal. Cabe avaliar se essa separação faz sentido
para o Shogun ou se é complexidade importada sem a dor que a justifica.

## 2. O que já existe, e que qualquer desenho deve reaproveitar

| Peça | Onde | Relevância aqui |
|---|---|---|
| `LLMProvider` (Protocol, 1 método) + 5 implementações | `core/llm/` | a fronteira de abstração **já existe** — é ela que um wrapper externalizaria |
| `SYSTEM_PROMPT` / `ESQUEMA_COMANDO` compartilhados | `core/llm/base.py` | `resposta_falada` é o **último** campo do schema — a base da opção (c) |
| `FallbackLLMProvider` + `LLMIndisponivelError` | `core/llm/fallback.py` | o fallback acontece **em volta da chamada inteira** — streaming muda isso (seção 5) |
| `UsoTokens` → `messages_uso` → `GET /consumo` | `core/llm/base.py`, `db/`, `api/consumo.py` | o payload do evento `done` **já é medido e persistido hoje** |
| Rota `/comando`: histórico antes, INSERT antes do LLM, gravação no fim | `api/comando.py` | tudo isso fica **fora** da camada de LLM — um wrapper não levaria nada disso junto |
| Autenticação Bearer + rate limit por token | `core/security.py`, `core/rate_limit.py` | um serviço separado precisaria de um segundo perímetro |
| Fala de `consultar_pendencias`/`abrir_app` montada pelo servidor | `api/comando.py` | streaming de LLM só beneficia `conversar` — fato já medido no streaming-design |
| Ollama como serviço HTTP local (`localhost:11434`) | `core/llm/ollama.py` | **o modelo local já é out-of-process** — ponto central da seção 3 |

## 3. Pergunta 1 — extrair um "shogun-wrapper" como serviço separado?

### Quando esse tipo de separação se paga

Gateways de LLM como serviço próprio existem, tipicamente, por uma ou mais
destas dores — vale nomeá-las porque nenhuma é "streaming":

1. **O motor de inteligência é um runtime de terceiros** que não pode viver
   dentro do processo principal (código externo, ciclo de deploy próprio,
   conflito de dependências) — o wrapper é a ponte.
2. **Vários frontends de naturezas diferentes** (backend web, bots, apps)
   consomem o mesmo cérebro — o wrapper é o ponto único de contrato e de
   autenticação interna entre serviços.
3. **Multiusuário com permissões** — o wrapper é a fronteira onde papel/escopo
   são impostos antes de o prompt ser montado.
4. **Deploy remoto** em que o wrapper é a unidade que sobe/desce/escala
   independente do resto.

### Por que nenhuma dessas dores existe no Shogun

- **O Shogun já ocupa a posição arquitetural do wrapper.** O desenho "um
  cérebro, vários clientes" ([architecture.md](architecture.md)) faz do
  servidor FastAPI exatamente o que o padrão chama de gateway: desktop e
  mobile são os frontends, e o servidor é o ponto único que autentica, monta
  prompt e fala com os provedores. Extrair `core/llm/` criaria um gateway
  **atrás** do gateway.
- **Os provedores não são um runtime de terceiros embutido — são chamadas de
  SDK/HTTP.** Claude, DeepSeek e OpenAI-mini são clientes de API de nuvem; e o
  caso que mais parece pedir um processo separado — o modelo local — **já é um
  processo separado**: o Ollama serve `hermes3:8b` em `localhost:11434`, e o
  `OllamaProvider` é só o cliente HTTP dele. Um shogun-wrapper seria um wrapper
  sobre um wrapper.
- **Usuário único, instância única.** Não há papéis a impor na fronteira, não
  há segundo consumidor da interpretação (nenhum processo além da rota
  `/comando` chama `LLMProvider`), não há escala independente a ganhar.
- **O custo é real e imediato.** Um serviço separado significa: segundo
  processo para o Marcus operar na mesma máquina; um segredo interno novo (ou
  duplicar o Bearer); uma classe nova de falha (wrapper fora do ar = um 503 que
  hoje não existe); serialização do `ComandoInterpretado` pelo fio; e a perda
  da injeção de dependência que sustenta a suíte — hoje os testes trocam o
  provedor com `app.dependency_overrides` em memória; com um wrapper, testar a
  rota exigiria mockar HTTP interno.
- **Não destrava nada do streaming.** A opção (c) precisa de um método de
  stream nos provedores e de uma rota SSE — as duas coisas cabem no processo
  atual sem nenhuma mudança de topologia. Separar não encurta nenhuma das ~3
  branches; alonga.

### Quando reavaliar

Gatilhos objetivos que reabririam a pergunta — espelhando o estilo dos
critérios de migração a Postgres em [DATABASE.md](DATABASE.md):

1. um **segundo consumidor** da interpretação de comandos, fora do servidor;
2. **multiusuário** com papéis/escopos distintos por usuário;
3. deploy em que a camada de LLM precise viver **noutra máquina** que o resto
   do servidor (ex.: GPU dedicada remota);
4. um provedor cuja integração exija **runtime embutido de terceiros** que não
   conviva com o processo FastAPI.

Nenhum vale hoje.

## 4. Pergunta 2 — o vocabulário de eventos, adaptado ao Shogun

A adaptação não é 1:1, porque o Shogun tem duas particularidades que um chat
puro não tem: a resposta é um **envelope estruturado** (`acao`, `parametros`,
`resposta_falada`), e em duas das três ações a fala **não vem do LLM**.

### `status` — progresso, e o anúncio antecipado da ação

Texto curto, curado pelo servidor, em pt-BR — mesmo espírito das mensagens
estáveis `_DETALHE_*` de `api/comando.py`: nunca eco de erro cru, nunca
conteúdo do modelo. Dois momentos naturais:

1. no início da interpretação ("Interpretando…" — opcional, talvez ruído);
2. **assim que o prefixo do envelope fecha** no scanner da opção (c): a `acao`
   chega nos primeiros ~15–30 tokens, então "Consultando suas pendências…"
   pode ser emitido segundos antes de a resposta existir. É o único ganho de
   streaming disponível para as ações cuja fala o servidor monta — e é um
   ganho que o desenho da opção (c) já previa ("a ação pode ser anunciada
   cedo") sem ter definido o veículo. `status` é o veículo.

### `chunk` — só o conteúdo de `resposta_falada`, em fronteira de frase

Confirma a hipótese do enunciado, com duas precisões:

- **Só para `conversar`.** Nas outras ações a fala é montada pelo servidor
  depois dos dados — não há geração a acompanhar; o cliente recebe `status` +
  `final` e nenhum `chunk` (ou um único). Isso precisa estar escrito no
  contrato para o cliente não tratar "zero chunks" como anomalia.
- **Fronteira de frase, agregada no servidor** — decisão que o
  streaming-design já inclinava: entregar em fronteira falável simplifica os
  dois clientes de uma vez e casa com o TTS. Ressalva honesta, herdada das
  medições reais (43–127 tokens de saída, 1–3 frases): com respostas desse
  tamanho, o stream típico terá **1 a 3 chunks**. O ganho é a primeira frase
  chegar ~1–2 s antes; não é um fluxo longo.

### `final` — o `CommandResponse` completo, não só o texto

**A adaptação mais importante, e onde o padrão de referência precisa mudar.**
Num chat puro, `final` é texto limpo. No Shogun, o cliente precisa de mais que
o texto: `actions` (com `ClientInstruction` dentro, no caso do `abrir_app`) e
`session_id` (que na primeira mensagem é onde o cliente descobre a sessão). E
as `actions` só existem depois da interpretação completa — nunca são
streamáveis por construção.

Logo: **`final` carrega o `CommandResponse` inteiro, idêntico ao que o
`POST /comando` devolve hoje.** Consequências boas e baratas:

- a regra "final é autoritativo, chunk é melhor-esforço" vira contrato: o
  cliente monta a exibição/fala definitiva a partir do `final`, e os chunks
  são só antecipação de TTS. Se o parse final da opção (c) corrigir/descartar
  a última frase, o `final` é quem manda;
- **degradação uniforme:** provedor sem streaming, fallback que assumiu antes
  do primeiro token, ou o `deterministico` (instantâneo) produzem um stream de
  `status?` + `final` + `done` — o cliente não distingue e não precisa
  distinguir. É o que permite o método de stream nascer **opcional** no
  `Protocol`, como o `aquecer()`;
- o `POST /comando` atual **continua existindo intacto** — a rota SSE é uma
  segunda porta para o mesmo envelope, não uma substituição.

### `done` — terminador sempre, uso de tokens como carona

Avaliação crítica do enunciado ("`done` com uso de tokens, aproveitando o
`GET /consumo`"): o Shogun **já** mede (`UsoTokens`), grava (`messages_uso`) e
expõe (`GET /consumo`) o consumo **no servidor** — nenhum cliente exibe token
hoje, e o rastreamento não precisa do evento para nada. O valor real do `done`
no Shogun **não é o payload; é ser terminador explícito**: com ele, o cliente
distingue "o stream acabou bem" de "a conexão caiu depois do `final`" (ou
antes dele), o que decide se o que foi falado merece confiança e se cabe
retry. Recomendação: manter o `done` **sempre emitido** (inclusive após um
`erro`), com o uso de tokens como payload opcional — já está na mão
(`ComandoInterpretado.uso`) e custa zero, mas o contrato deve dizer que o
cliente pode ignorá-lo, e que `uso` ausente é normal (`deterministico` não
mede).

### `erro` — o quinto evento, que o padrão original não tem

No padrão estudado, falha vira texto dentro do próprio stream. Para o Shogun
isso é insuficiente: erro embutido em `chunk` iria direto para o TTS. Melhor
um evento tipado `erro`, com a mensagem **sanitizada e estável** (precedente:
`_DETALHE_LLM_INDISPONIVEL`), seguido de `done`. Ele só aparece no caso que o
streaming-design já identificou como irrecuperável: falha **depois** do
primeiro chunk repassado, quando trocar de provedor silenciosamente deixou de
ser possível. Antes do primeiro chunk, o fallback resolve e o cliente nem
sabe.

### Resumo do contrato proposto

```
POST /comando/stream            (mesmo corpo do POST /comando; Accept: text/event-stream)

event: status   data: {"text": "Consultando suas pendências…"}     0..n vezes
event: chunk    data: {"text": "Você tem duas pendências."}        0..n vezes (fronteira de frase)
event: final    data: {CommandResponse completo}                   exatamente 1 (exceto após erro)
event: erro     data: {"detail": "<mensagem estável>"}             0..1 (só falha pós-primeiro-chunk)
event: done     data: {"uso": {...} | null}                        exatamente 1, sempre o último
```

A persistência não muda de lugar: a fala gravada em `messages` é a do `final`,
gravada no fim do stream — como o passo 8 do [DESIGN.md](DESIGN.md) já
prescreve para o cenário com streaming.

## 5. Streaming nativo dos provedores × fallback — verificado no código

**Fato verificado (leitura de `core/llm/` neste worktree): nenhuma das cinco
implementações streama hoje.** `ClaudeProvider` usa `messages.create(...)` sem
stream; `openai_compat.py` chama `chat.completions.create(...)` sem
`stream=True`; `ollama.py` manda `"stream": False` explícito no payload (com
comentário dizendo que a rota quer a resposta inteira); `deterministico` não
gera nada — responde inteiro, instantâneo.

O que as **APIs** por trás suportam — repetindo a tabela do streaming-design
com o grau de confiança dela, que esta leitura de código não altera:

| Provedor | Streaming nativo da API | Streaming **junto com** o schema fechado | Confiança |
| --- | --- | --- | --- |
| claude | sim (SSE nativo do SDK; `anthropic` 0.87.0 instalado) | sim — o JSON do `output_config.format` chega como deltas | alta |
| openai_mini | sim (`stream=True`; `openai` 2.24.0 instalado) | sim — json_schema strict convive com stream | alta |
| deepseek | sim (mesmo protocolo OpenAI) | JSON mode + stream convivem, **sem** enforcement de schema | média — **verificar** |
| ollama | sim (`/api/chat` com `stream: true`) | gramática + stream convivem em tese | média — **verificar na versão instalada** |
| deterministico | não se aplica | não se aplica — resposta inteira, instantânea | alta (é nosso) |

Nada disso foi exercitado contra API real neste estudo (norma do projeto:
nenhum teste chama API real; e este é um documento, não um teste). Os dois
"verificar" continuam sendo tarefa da primeira branch da opção (c).

### O caso central: principal streama, fallback não

O `FallbackLLMProvider` de hoje funciona porque envolve a **chamada inteira**:
`interpretar_comando` ou devolve o comando validado ou levanta
`LLMIndisponivelError`, e o reserva repete a chamada do zero. Streaming quebra
essa simetria em três cenários, todos com resposta limpa no desenho da seção 4:

1. **Principal falha antes do primeiro chunk repassado** (não conectou,
   timeout no arranque, prefixo do envelope inválido): o fallback assume
   exatamente como hoje. Se o reserva não streama — incluindo o
   `deterministico`, que nunca falha e responde na hora — o cliente recebe
   `final` + `done` sem chunks. **A degradação uniforme do `final` absorve a
   assimetria: o contrato nunca promete chunks.** Nota a favor: com agregação
   por frase e respostas de 1–3 frases, a janela "nenhum chunk repassado
   ainda" cobre a maior parte da geração — o fallback limpo é o caso comum,
   não o raro.
2. **Principal falha depois de chunk repassado**: a primeira frase já pode ter
   sido falada pelo TTS; trocar de provedor silenciosamente produziria uma
   resposta com duas personalidades ou uma repetição. Sem conserto bom:
   `event: erro` + `done`, cliente decide o que dizer. (É a mesma conclusão do
   streaming-design; aqui ela só ganha o evento que a transporta.)
3. **Reserva streama e principal não** (configuração invertida): irrelevante —
   o wrapper de fallback só streama o que o provedor **ativo** entrega; cada
   caminho degrada sozinho.

Consequência para a implementação (registro, não decisão): o método de stream
nasce **opcional** no `Protocol` (como `aquecer()`), o `FallbackLLMProvider`
ganha a variante streamada com a regra "troca só antes do primeiro chunk
repassado", e o caminho não-streamado de todos os provedores fica intacto —
nenhum dos cinco é reescrito.

## 6. Recomendação

**Não extrair serviço separado — e adotar o vocabulário SSE adaptado
(`status`/`chunk`/`final`/`erro`/`done`) como o contrato-alvo da opção (c),
implementado dentro do servidor FastAPI atual, quando o streaming entrar.**

Em ordem de peso:

1. **O shogun-wrapper é prematuro — e provavelmente desnecessário em
   caráter permanente.** As quatro dores que justificam um gateway separado
   (runtime de terceiros, múltiplos frontends, multiusuário, deploy
   independente) não existem no Shogun — e a que mais parece existir já foi
   resolvida por outro processo: o Ollama. O servidor central **é** o wrapper
   do ponto de vista dos clientes. Separar agora custaria um processo, um
   segredo, uma classe de falha e a simplicidade da injeção de dependência,
   sem destravar nada.
2. **O que vale trazer do padrão não é a topologia — é o contrato de
   eventos.** `final` autoritativo com o `CommandResponse` completo, `done`
   sempre emitido como terminador, degradação "zero chunks é normal", `status`
   como veículo do anúncio antecipado da ação, `erro` tipado e sanitizado.
   Tudo isso cabe no processo atual, casa com a opção (c) já escolhida e não
   exige tocar em nenhum provedor antes da hora.
3. **O timing não muda.** Este documento não antecipa o streaming — a decisão
   do streaming-design (v1.0 sem streaming; implementar quando a espera
   incomodar) continua de pé. O que muda é que, quando a primeira branch da
   opção (c) abrir, o contrato do fio já estará decidido em vez de ser
   improvisado nela.

Custo estimado quando entrar (refinando a estimativa de 3 branches do
streaming-design, sem alterá-la): (1) scanner incremental + método opcional de
stream em 1–2 provedores + fallback streamado; (2) rota `POST /comando/stream`
com os 5 eventos — sem dependência nova se for `StreamingResponse` com
`text/event-stream` à mão, ou com uma dependência pequena de SSE se a
ergonomia compensar (decisão da branch); (3) desktop consumindo SSE + TTS por
frase. A regra de consumo (`final` × `chunk`) precisa nascer com rede mecânica
nos moldes de `text` × `fallback_text` — docstring nos dois lados **e** teste
que a exercite, para não repetir a lição do `ClientInstruction`.

## 7. O que precisa de aval do Marcus

1. **Descartar o shogun-wrapper como serviço separado** (com os quatro
   gatilhos de reavaliação da seção 3 registrados). É a recomendação; a
   decisão é sua.
2. **Adotar o vocabulário de 5 eventos** (`status`/`chunk`/`final`/`erro`/
   `done`) como contrato-alvo do streaming — em particular a escolha de
   `final` = `CommandResponse` completo, que é o que amarra os clientes.
3. **`done` com ou sem uso de tokens no payload.** Recomendação: com, opcional
   e ignorável — mas é contrato de fio, e contrato de fio é decisão sua.
4. **`erro` como evento tipado** (em vez de erro-como-texto no stream) — muda
   o que os dois clientes precisam implementar.
5. Registro em [DESIGN.md](DESIGN.md)/[ROADMAP.md](ROADMAP.md) de que a
   pergunta "SSE ou WebSocket" fica respondida como **SSE** para este fluxo
   (servidor→cliente, um sentido só) — o WebSocket previsto na arquitetura
   continua reservado para a conversa em tempo real com STT, que é outro
   fluxo.
