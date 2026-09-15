# STT no desktop — opções, trade-offs e recomendação

> Documento de decisão, escrito **antes** de qualquer implementação. A
> recomendação explícita está na seção 8; o que ela ainda exige de aprovação
> humana está na seção 9. Nenhuma linha de código, contrato ou permissão muda
> neste documento.
>
> Convenção de honestidade, usada no texto inteiro: **[projeto]** = fato
> verificado no código ou nos docs deste repositório nesta sessão;
> **[externo: fonte]** = leitura de documentação de terceiros, com a fonte
> nomeada, não exercitada aqui; **[suposição]** = estimativa ou expectativa,
> sem verificação. Nenhum número aparece sem uma dessas marcas.

## 1. O buraco

O Shogun se define como **assistente pessoal de voz** desde a primeira linha
do `CLAUDE.md` — e hoje a voz só existe na saída. O desktop **fala** as
respostas (TTS via `speechSynthesis` do WebView2, PR #31), mas o comando
entra **digitado**: o passo 1 do fluxo em `docs/DESIGN.md` ("cliente manda
comando de voz transcrito") está marcado ✅ apenas porque o servidor de fato
recebe texto — o "transcrito" é o Marcus datilografando. A metade que falta é
exatamente a que dá nome ao projeto. [projeto]

A decisão de arquitetura já está tomada e vale como premissa, não como opção
a reabrir: **o STT roda no cliente, por latência — o servidor nunca recebe
áudio** (`docs/architecture.md`, "Decisões em aberto"; `docs/DESIGN.md`,
passo 1). Também está decidido o **quando**: fora da v1.0, entra na v1.1
(`docs/ROADMAP.md`; decisão do Marcus registrada em
`.maestri/pr-pendente-feature-desktop-tts.md`: "TTS agora, STT na v1.1").
[projeto]

O que **não** está decidido é todo o resto, e é o que este documento existe
para preparar: como capturar o áudio, qual motor transcreve, qual UX dispara
a captura, e em quantas branches isso entra. A estimativa registrada é
"captura nativa (plugin Tauri/Rust) + whisper.cpp local ou API + UX de
push-to-talk; 2–3 branches + decisões de motor/modelo/hotkey"
(`.maestri/proximas-rodadas.md`). [projeto]

Uma restrição de máquina condiciona a decisão de motor inteira e por isso
vem já aqui: a GPU disponível é uma **RTX 4050 Laptop com 6 GB de VRAM**, e
ela **já serve o `hermes3:8b` do Ollama** — ~4,7 GB de pesos em Q4_K_M mais
~1 GB reservado para contexto, pelos números do próprio
`server/README.md`. [projeto] A aritmética é direta: **sobram ~0,3 GB de
VRAM**. Qualquer desenho que ponha o STT na GPU disputa memória com o
cérebro do Shogun.

## 2. O que já existe, e que qualquer opção deve reaproveitar

| Peça | Onde | Relevância aqui |
|---|---|---|
| TTS atrás de interface pequena (`falar`/`calar`) | `desktop/src/lib/voz.ts` | `calar()` é idempotente e já cancela fala em curso — é a arma pronta contra o eco quando o microfone abrir |
| Padrão de teste do lado de voz | `desktop/src/lib/voz.test.ts` | módulo puro, globais dubladas (`vi.stubGlobal`), e a honestidade registrada: *"ouvir continua sendo humano"* — o STT herda o mesmo teto: testa-se tudo **antes** do som entrar |
| Envio de comando pronto | fluxo do chat → `POST /comando` (timeout 60 s, retry em 503, checagem de `/health`) | o texto transcrito entra **aqui**, no mesmo lugar do texto digitado — resiliência já paga |
| Capabilities com escopo mínimo | `desktop/src-tauri/capabilities/default.json` | não há **nenhuma** permissão de microfone hoje; a lição do incidente do escopo http (comentário em `instrucoes.ts`) vale de novo: *a permissão no capabilities é parte da feature, não detalhe* |
| Rede mecânica código ↔ capabilities | `instrucoes.escopo.test.ts` | precedente de teste que prende um acoplamento por string invisível ao `tsc` e ao `cargo` — permissão nova deve ganhar rede análoga |
| Plugins Tauri já integrados | `src-tauri/Cargo.toml`: `http`, `shell`, `store` | o padrão de adoção de plugin (dep no Cargo + pacote JS + entrada no capabilities) está estabelecido; **não** há plugin de hotkey global nem de áudio hoje |
| Ollama servindo o LLM local na GPU | `server/` + nota de máquina em `CONTEXTO-GERAL.md` §4.2 | o ocupante dos 6 GB de VRAM — restrição central da seção 4 |
| WebSocket reservado para "conversa em tempo real com STT" | `docs/shogun-wrapper-design.md` §7.5 | fixa a fronteira da seção 6: a v1.1 **não** é esse fluxo |
| Medições de latência do uso real | `docs/streaming-design.md` §2 | mediana de 4,1 s do comando inteiro (ollama aquecido) — a régua contra a qual a latência do STT deve ser lida |

Duas consequências desta tabela valem adiantar:

1. **O servidor não muda. `shared/` não muda.** O STT é 100% cliente: áudio
   vira texto no desktop e o texto entra no mesmo `POST /comando`. Nenhum
   contrato novo, nenhuma paridade a manter, nenhum teste de servidor
   tocado. É a feature mais isolada do backlog — raro, e vale proteger esse
   isolamento nas escolhas abaixo. [projeto]
2. **A latência do STT tem uma régua.** O comando hoje leva ~4 s de mediana
   entre enviar e ouvir a resposta [projeto]. Um STT local que gaste 1–2 s
   transcrevendo uma fala curta muda pouco a espera total; um que gaste 10 s
   arruína a feature. É esse o número que o spike da primeira branch precisa
   medir — não "qual é o melhor motor em benchmark".

## 3. Captura de áudio

### 3.1 O que o WebView2 oferece — e a afirmação a re-verificar

A afirmação registrada no projeto é: **`SpeechRecognition` não existe no
WebView2** — foi ela que empurrou o STT para fora da v1.0
(`.maestri/relatorio-shogun-contexto.md`, repetida em `status-geral.md`).
[projeto — como afirmação registrada, **não** re-verificada nesta sessão]

A leitura externa é consistente com ela: a Web Speech API tem duas metades, e
no Chromium o **reconhecimento** (`SpeechRecognition`) historicamente depende
de um serviço do Google que os empacotamentos do WebView2 não trazem; a
documentação da Microsoft lista lacunas de API entre o Edge e o WebView2.
[externo: docs da Microsoft sobre WebView2; detalhe não re-verificado] A
**síntese** (`speechSynthesis`) existe e o projeto a usa em produção — o que
prova que "WebView2 tem metade da Web Speech API" não é contradição, é o
estado real. [projeto]

**Tratamento honesto:** a primeira branch deve gastar meia hora
re-verificando `("SpeechRecognition" in window)` no WebView2 real. Se a
afirmação cair (uma atualização do runtime pode mudá-la), `SpeechRecognition`
ainda **não** seria o caminho certo — o reconhecimento do Chromium manda
áudio para serviço externo, o que esbarra na mesma tensão local-first da
seção 4.2 — mas o documento deixaria de citar uma ausência como motivo.

Já **`getUserMedia` + `MediaRecorder`/Web Audio existem no WebView2** — são
APIs do Chromium comum, e o caminho a avaliar. [externo: docs
MDN/Microsoft; a existência é consenso documental, o comportamento do prompt
de permissão dentro do Tauri é o que o spike confirma]

### 3.2 As opções de captura

#### A. `getUserMedia` no próprio WebView (JS puro)

Capturar no frontend: `getUserMedia({ audio: { echoCancellation: true, ... } })`
e extrair PCM via Web Audio (`AudioWorklet`), ou gravar via `MediaRecorder`.

- **A favor:** zero Rust novo; o módulo nasce como `voz.ts` — função pura por
  cima de uma API global, testável no vitest com `vi.stubGlobal`, dentro da
  norma "teste de módulo puro" da suíte [projeto]; o pipeline de constraints
  do Chromium traz cancelamento de eco e supressão de ruído de graça
  [externo: MDN, `MediaTrackConstraints`]; nenhuma permissão nova no
  capabilities — microfone via webview não passa pelo sistema de permissões
  do Tauri (ver 3.3).
- **Contra:** o formato nativo do `MediaRecorder` é WebM/Opus, e whisper.cpp
  consome PCM 16 kHz mono — ou se captura PCM direto via `AudioWorklet`
  (mais código JS, sem re-encode), ou se decodifica no Rust [externo: README
  do whisper.cpp exige 16 kHz]; o comportamento do **prompt de permissão** do
  WebView2 embutido no Tauri (aparece? com que origem? persiste?) é
  exatamente o tipo de coisa que só o spike responde — há relatos históricos
  de fricção, não verificados aqui [suposição].
- **Transporte JS→Rust:** o áudio precisa chegar ao motor. Um comando
  `invoke` com o buffer (Tauri 2 suporta payload binário) resolve; o custo de
  serializar alguns segundos de PCM 16 kHz mono (~32 KB/s) é desprezível
  [externo: aritmética sobre o formato; taxa = 16000 amostras/s × 2 bytes].

#### B. Captura nativa em Rust (`cpal`)

Um comando Tauri (`iniciar_captura`/`parar_captura`) usando `cpal` (WASAPI
no Windows) para capturar PCM direto no processo Rust.

- **A favor:** PCM 16 kHz sem conversão nem travessia JS→Rust do áudio; o
  buffer nasce ao lado do motor (seção 4) e nunca entra no webview; sem
  dependência do comportamento de permissão do WebView2 — resta só a
  permissão de SO (3.3). [externo: docs do cpal; avaliação minha]
- **Contra:** dependência Rust nova + código de threading de áudio (callbacks
  do cpal rodam em thread própria); resampling manual se o dispositivo não
  oferecer 16 kHz nativo; **fora do alcance da suíte** — a norma do desktop é
  vitest de módulo puro com o plugin mockado [projeto], então a captura Rust
  só é testável mockando o `invoke`, e o miolo real fica 100% manual, como o
  bloco F8 do roteiro de regressão ficou para o TTS [projeto]; sem
  cancelamento de eco de graça — o AEC do Chromium fica para trás [suposição
  razoável: WASAPI cru não aplica AEC].

#### C. Plugin de comunidade pronto

Não há plugin **oficial** de gravação de áudio para Tauri 2 desktop; o que
existe na comunidade não foi avaliado aqui. [externo: catálogo de plugins do
Tauri; afirmação de ausência **não re-verificada** — o spike confere] Adotar
dependência de terceiro pouco mantida para um caminho que as opções A/B
cobrem com API de plataforma é risco sem contrapartida clara. Descartada
como aposta inicial; fica como atalho se o spike da A tropeçar no prompt de
permissão e alguém já tiver resolvido exatamente isso.

### 3.3 Permissões — Windows e capabilities

Duas camadas, e nenhuma delas é o capabilities do Tauri:

1. **Privacidade do Windows.** Configurações → Privacidade e segurança →
   Microfone tem a chave "Permitir que aplicativos da área de trabalho
   acessem seu microfone" — apps desktop (o Shogun incluso) são governados
   por ela, não por permissão por app da loja. Desligada, tanto a opção A
   quanto a B recebem silêncio/erro. [externo: comportamento documentado do
   Windows 10/11; não exercitado nesta sessão] O tratamento é UX, não código
   de permissão: detectar a falha e explicar onde ligar.
2. **WebView2 (só opção A).** O `getUserMedia` dispara o fluxo de permissão
   do próprio WebView2 (`PermissionRequested`); como o Tauri o trata por
   default — se mostra prompt, se lembra a escolha — é ponto explícito do
   spike. [externo: docs do WebView2; comportamento dentro do Tauri não
   verificado]

O **capabilities de hoje não menciona microfone** — e continua assim nas
opções A e B: o sistema de permissões do Tauri governa plugins e comandos,
não o acesso do webview a mídia. [projeto: `default.json` lido; leitura
externa: modelo de capabilities do Tauri 2] O que **muda** no capabilities
nesta feature é outra coisa:

- **hotkey global (seção 5):** `tauri-plugin-global-shortcut` + permissões
  novas (`global-shortcut:allow-register` etc.) — superfície nova, mesma
  liturgia dos plugins existentes. [externo: docs do plugin]
- **whisper.cpp como sidecar (se a seção 4 escolher esse formato):** entrada
  nova no escopo `shell`, que hoje trava exatamente 4 comandos [projeto]. A
  alternativa via binding (`whisper-rs`) não toca o escopo.

A lição do incidente do escopo http se aplica dobrada: **cada entrada nova no
capabilities entra na mesma branch da feature que a exige, com rede mecânica
no molde de `instrucoes.escopo.test.ts` quando houver acoplamento por
string.** [projeto]

## 4. Motor

### 4.1 whisper.cpp local — e a disputa de VRAM que não existe se não for criada

Números do README do whisper.cpp (formato ggml, memória total aproximada por
modelo): [externo: README do whisper.cpp; **não re-verificados nesta
sessão** — conferir na branch do motor]

| Modelo | Disco | Memória ~ | Nota |
|---|---|---|---|
| tiny | ~75 MB | ~273 MB | multilíngue fraco; pt sofre |
| base | ~142 MB | ~388 MB | mínimo honesto para pt |
| small | ~466 MB | ~852 MB | o candidato — qualidade/custo |
| medium | ~1,5 GB | ~2,1 GB | melhor pt, custo alto |

A pergunta do ROADMAP — "qual modelo cabe em 6 GB junto com o hermes3:8b" —
tem resposta desconfortável e é melhor dizê-la de frente: **na GPU, nenhum
cabe com folga.** O hermes3:8b ocupa ~5,7 GB dos 6 GB (pesos + contexto,
números do `server/README.md` [projeto]); os ~0,3 GB restantes não acomodam
nem o tiny com segurança. As saídas seriam despejar o LLM para CPU quando o
microfone abre (troca o poste maior — mediana de 4,1 s — por um pior) ou
aceitar swap de VRAM imprevisível. As duas são ruins.

**A resposta boa é não disputar: whisper.cpp em CPU.** O whisper.cpp nasceu
otimizado para CPU (é o seu caso de uso primário) [externo: README do
projeto], e a carga do Shogun é a menor possível — falas de comando de
poucos segundos, não ditado de reunião. A expectativa de ordem de grandeza é
o base/small transcrevendo um comando de ~5 s em ~1–3 s num laptop moderno —
**[suposição; ordem de grandeza, não medição]** — contra a régua de 4,1 s do
resto do pipeline. O spike da branch do motor mede isso na máquina real
antes de qualquer polimento; se o small passar de ~3 s, o base assume.

Formato de integração, duas vias:

- **`whisper-rs` (binding Rust)** — o motor vive no processo do app; sem
  sidecar, sem mudança no escopo `shell`, distribução em um binário só.
  Custo: toolchain C/C++ (CMake) no build do desktop, que hoje é só
  Rust+Node. [externo: repositório whisper-rs; custo de build = suposição
  informada]
- **sidecar (binário `whisper.cpp` + `shell`)** — build desacoplado, mas:
  entrada nova no escopo shell [projeto: como o escopo funciona], processo
  filho por transcrição ou servidor local persistente, e distribuição de um
  executável a mais. Mais peças móveis para o mesmo resultado.

O **modelo não se embute no instalador**: ~466 MB no small inflaria o bundle
por um arquivo que muda por escolha do usuário. Download no primeiro uso,
com checksum, para o diretório de dados do app — o lado Rust baixa sem
permissão nova. Decisão de operação análoga ao `ollama pull`: o repositório
não fixa o modelo, quem opera escolhe (precedente: `OLLAMA_MODEL`
[projeto]).

### 4.2 API de nuvem

OpenAI (whisper-1 e sucessores), Deepgram, Groq e afins transcrevem um
comando curto com boa qualidade e latência de rede na casa de ~0,5–2 s
[suposição; não medido]. Custo publicado da OpenAI na casa de US$ 0,006/min
[externo: tabela de preços da OpenAI; **não re-verificado** — conferir se a
decisão pender para cá]. Para falas de segundos, o custo mensal seria
centavos — **o dinheiro não é o argumento contra.**

O argumento contra é o que o projeto já escolheu uma vez: o Ollama existe
para "operar sem custo de API e **sem mandar comandos pessoais para fora da
máquina**" (`CONTEXTO-GERAL.md` §2.4 [projeto]). O STT de nuvem manda o
**áudio da voz do Marcus** para fora — dado mais sensível que o texto que o
LLM de nuvem veria no fallback. Adotar nuvem como motor **primário** de STT
contradiria a razão de ser do provedor local; como **opcional atrás da mesma
interface**, é upgrade legítimo — o mesmo desenho do TTS ("voz natural fica
como upgrade futuro atrás da mesma interface", `voz.ts` [projeto]).

Há também uma dependência dura: sem rede, um Shogun com STT só de nuvem fica
**mudo na entrada** — sendo que o resto do pipeline (Ollama + servidor
local) funciona inteiro offline hoje. [projeto]

### 4.3 "Local primeiro com fallback" — por que o padrão do LLM não transfere inteiro

A tentação é copiar o par `ollama` + `deepseek`: local primeiro, nuvem
quando falha. Mas o fallback do LLM funciona porque existe um **oráculo
mecânico de falha**: JSON fora do schema fechado vira `LLMIndisponivelError`
e dispara a troca [projeto]. **O STT não tem oráculo equivalente** — uma
transcrição ruim é uma string plausível; nada no cliente sabe que "abrir a
calculadora" virou "a brir a cal cu ladora" antes de o LLM tropeçar nela. O
fallback de STT só se acionaria por falha **dura** (motor não carregou,
modelo ausente, crash) — casos raros e quase todos de configuração, não de
runtime.

Conclusão honesta: **fallback de nuvem para STT não vale a complexidade na
v1.1.** O que vale é a interface preparada para ele — um módulo
`transcrever(audio) -> texto` cuja implementação é trocável, exatamente como
`falar()` esconde o `speechSynthesis`. Se a qualidade do small decepcionar
em uso real, a decisão de nuvem reabre com dados.

### 4.4 Modelo: multilíngue oficial vs fine-tune pt

Não existe modelo Whisper **oficial** pt-only; o que existe são os
multilíngues com o parâmetro de idioma fixável (`language: "pt"`) e
fine-tunes comunitários de português no Hugging Face, que exigiriam
conversão para ggml e manutenção própria. [externo: ecossistema
Whisper/HF; não avaliado em profundidade] Recomendação: **small multilíngue
oficial com `language` fixado em pt** — o idioma do Shogun é fixo por
identidade (`SYSTEM_PROMPT` fala pt-BR [projeto]), então nem detecção
automática de idioma é necessária, o que também poupa latência. Fine-tune
comunitário só se o uso real mostrar erro sistemático de pt-BR — e aí é
troca de arquivo de modelo, não de código, se a interface da 4.3 for
respeitada.

Nota de simetria com o LLM local: a gramática do Ollama garante a forma e
não a semântica [projeto]; no STT nem forma há. O julgamento final de
qualidade é o mesmo de lá — uso real, com o texto transcrito **visível** na
UI antes de virar comando (seção 5), para o Marcus ver o que o Shogun achou
que ouviu.

## 5. UX

### 5.1 O gatilho: botão, hotkey global, VAD

**Botão na UI (segurar para falar, ou toque liga/desliga).** Custo mínimo:
um componente React, nenhum plugin, nenhuma permissão. Limite real: exige a
janela visível — para um assistente que se quer ambiente, é o degrau de
entrada, não o destino.

> **Decisão (15/09/2026): o botão alterna, não segura.** A v1.1 nasceu
> segurar-para-falar e a primeira regressão manual derrubou essa escolha por
> três motivos, nessa ordem: ditado longo cansa a mão; segurar prende o
> ponteiro numa janela que o usuário pode querer usar enquanto fala; e o
> teclado sai de graça, porque um `<button>` com `onClick` já responde a
> espaço e enter — sem `keydown`/`keyup` com guarda de auto-repeat, sem
> `setPointerCapture`, sem `pointercancel`. Os seis handlers viraram um.
>
> O que a troca **não** muda: `calar()` continua antes de abrir o microfone
> (§5.3), e a fase `abrindo` continua descartando a captura de quem desiste
> antes de o `cpal` resolver — ela cobre a corrida do dispositivo, não o
> gesto. A hotkey global abaixo continua sendo push-to-talk de verdade e
> segue no radar: alternar por clique e segurar por tecla global convivem.

**Hotkey global (push-to-talk de verdade).** O Tauri 2 tem plugin oficial
(`tauri-plugin-global-shortcut`) [externo: docs do Tauri]; o custo é a
liturgia conhecida (Cargo + pacote JS + permissões novas no capabilities
[projeto: padrão dos plugins atuais]) mais dois pontos que não são código:
**escolher a combinação** (colisão com atalhos de outros apps é conflito
silencioso — o registro falha ou rouba o atalho alheio [externo: natureza
documentada de global shortcuts no Windows]) e **capturar com a janela em
segundo plano** — microfone aberto sem UI visível pede um indicador honesto
(o Windows 11 mostra o ícone de microfone na bandeja por conta própria
[externo: comportamento do SO; não verificado]).

**VAD / wake word ("Shogun, ...").** Microfone **sempre** aberto, detecção
de fala ou de palavra-chave. É o JARVIS de verdade e é também: consumo
contínuo, autoescuta do próprio TTS (ver 5.3), um modelo a mais (wake word),
e a decisão de privacidade de um mic permanentemente quente. Nada disso é da
v1.1. Fica registrado como evolução natural **depois** que captura + motor
existirem — VAD é um gatilho diferente sobre o mesmo pipeline.

Recomendação de escada: **botão primeiro (v1.1 mínima), hotkey global na
sequência (ainda v1.1 se couber), VAD/wake word fora.**

### 5.2 Feedback visual e o texto transcrito

Três estados novos na UI: **gravando** (mic aberto — indicador inequívoco,
por honestidade antes de estética), **transcrevendo** (mic fechado, motor
rodando — é onde o 1–3 s da seção 4.1 vive) e **pronto** (texto no fluxo).
E uma decisão pequena com consequência: o texto transcrito **aparece antes
de ir ao servidor**. Recomendação: aparece **e vai direto** — parar para
confirmar mataria a fluidez que justifica a feature; a correção é a bolha
do usuário mostrando o que foi entendido, e o histórico já guarda o resto
[projeto: fluxo de mensagens existente]. Errou feio, o Marcus manda de novo
— mesmo contrato de confiança do LLM local.

### 5.3 O TTS quando o microfone abre — eco

O caso concreto: o Shogun está falando a resposta anterior e o Marcus aperta
para falar. Sem tratamento, o microfone grava a voz do próprio Shogun.

O projeto já tem a ferramenta exata: **`calar()` em `voz.ts` — idempotente,
cancela a fala em curso** [projeto]. Regra: **abrir o microfone chama
`calar()` primeiro, sempre.** Isso resolve o push-to-talk por construção —
com gatilho manual, o usuário decide quando falar, e o Shogun cala para
ouvir (comportamento de assistente correto também como UX). O
`echoCancellation` do `getUserMedia` (opção A da seção 3.2) é cinto de
segurança adicional para som residual do sistema [externo: MDN]. O problema
do eco **sem** solução barata é o do VAD (mic aberto durante o TTS) — mais
um motivo para ele ficar fora da v1.1.

## 6. Integração — o que muda no fio (nada) e o que fica para o WebSocket

**O texto transcrito entra no mesmo lugar do texto digitado.** O fluxo do
chat já resolve tudo o que importa: `POST /comando` com sessão, timeout de
60 s, retry no 503, checagem de `/health`, TTS da resposta [projeto]. O STT
da v1.1 é um **produtor de texto** plugado na frente desse fluxo — nenhuma
rota nova, nenhum campo novo, nenhuma mudança em `shared/`, zero trabalho de
servidor. O teste de paridade de contratos nem fica sabendo.

A fronteira com o futuro está escrita em `shogun-wrapper-design.md` §7.5: o
WebSocket previsto na arquitetura "continua reservado para a conversa em
tempo real com STT, que é outro fluxo" [projeto]. Nomeando a divisão:

| | v1.1 (este documento) | Fase WebSocket (fora) |
|---|---|---|
| Unidade | fala discreta: aperta, fala, solta, texto pronto | áudio contínuo streamado enquanto fala |
| Transcrição | ao final da captura, uma vez | incremental, com parcial revisável |
| Transporte | o `POST /comando` de hoje | WebSocket bidirecional |
| Interrupção (barge-in) | não — `calar()` manual | sim, cortar o TTS falando por cima |
| Custo de servidor | zero | rota WS + protocolo novo |

A v1.1 entrega a primeira coluna inteira e nada da segunda — e a segunda
**reaproveita** captura e motor da primeira (streaming de STT local é o
mesmo whisper chamado de outro jeito). Não há trabalho jogado fora.

## 7. Ordem de implementação — as branches e o corte mínimo

Confirmando a estimativa de 2–3 branches do ROADMAP, com conteúdo:

**Branch 1 — `feature/desktop-captura-voz`: captura + UX mínima.**
O spike decide a opção da seção 3.2 na prática: re-verificar a ausência de
`SpeechRecognition` [projeto: afirmação registrada a confirmar], exercitar
`getUserMedia`/prompt de permissão no WebView2 real, extrair PCM 16 kHz.
Entrega: botão segurar-para-falar, indicador de gravação, `calar()` ao
abrir o mic, e o módulo `microfone.ts` (ou o comando Rust, se o spike
empurrar para a opção B) com testes no molde de `voz.test.ts`. Sem motor
ainda: o áudio capturado morre num log/dev — a branch é funcional
isoladamente (nada de UI quebrada esperando o motor: o botão pode entrar
oculto atrás de flag de config, precedente do `tauri-plugin-store`
[projeto]).

**Branch 2 — `feature/desktop-stt-whisper`: motor + integração.**
`whisper-rs` (ou sidecar, se o build com CMake atolar — decisão da branch,
com o custo de capabilities anotado na seção 3.3), download do modelo no
primeiro uso com checksum, `transcrever(audio) -> texto` atrás de interface
trocável, texto entrando no fluxo de envio existente. Medição real de
latência na máquina do Marcus registrada no PR (a régua: mediana de 4,1 s do
pipeline atual [projeto]). **Ao final desta branch, o Shogun ouve.**

**Branch 3 — `feature/desktop-hotkey-ptt`: push-to-talk global.**
Plugin `global-shortcut` + permissões no capabilities + escolha de
combinação + comportamento com janela em background. Deliberadamente
separada: é a única com superfície de permissão nova, e é a que pode
escorregar sem quebrar a promessa.

**O corte mínimo honesto da v1.1 são as branches 1+2.** Com elas, "o
assistente de voz aceita voz" deixa de ser falso — pelo botão. A branch 3
transforma isso em push-to-talk de verdade e é o alvo desejado da v1.1, mas
é qualidade sobre a feature, não a feature. VAD, wake word, STT de nuvem e
conversa contínua via WebSocket ficam explicitamente fora.

## 8. Recomendação

**whisper.cpp local rodando em CPU (modelo small multilíngue com idioma
fixado em pt, base como plano B de latência), captura preferencialmente via
`getUserMedia` no WebView2 com PCM extraído no cliente (decisão final no
spike da branch 1, com `cpal` nativo como alternativa), push-to-talk por
botão na UI entrando primeiro e hotkey global na branch seguinte, texto
transcrito entrando no `POST /comando` de hoje — servidor e `shared/`
intocados, nuvem e WebSocket fora da v1.1.**

Em ordem de peso:

1. **CPU, não GPU — porque a GPU já tem dono.** Os 6 GB da RTX 4050 estão
   ~95% ocupados pelo hermes3:8b [projeto: aritmética sobre números do
   `server/README.md`]. Disputar VRAM degradaria o poste maior da latência
   (o LLM) para acelerar o menor (falas de segundos). O whisper.cpp em CPU é
   o desenho que não briga com ninguém — e se a latência medida no spike
   contrariar a expectativa [suposição a verificar], o plano B é o modelo
   base, não a GPU.
2. **Local, não nuvem — pela mesma razão que o Ollama existe.** O projeto já
   pagou o preço do local-first para não mandar comandos para fora da
   máquina; a voz é mais sensível que o texto. Custo zero e offline completo
   vêm de brinde. Nuvem fica como upgrade atrás da interface `transcrever()`
   — o mesmo desenho já usado no TTS.
3. **Sem fallback de nuvem na v1.1 — porque não há oráculo.** O par
   local+fallback do LLM funciona porque o schema detecta a falha; STT ruim
   é string plausível, indetectável no cliente. Fallback só cobriria falha
   dura de configuração — não paga a complexidade agora.
4. **A UX entra em escada** — botão (nada de permissão nova), depois hotkey
   global (a única superfície de permissão nova da feature, isolada na
   própria branch), VAD nunca nesta versão. Microfone aberto chama `calar()`
   sempre — o eco do TTS morre por construção no push-to-talk.
5. **O isolamento é um ativo: zero servidor, zero contrato.** Nenhuma opção
   recomendada toca `shared/`, rotas ou testes de servidor. As decisões que
   sobram são todas do cliente — e por isso a lista da seção 9 é curta e
   concreta.

## 9. O que precisa de aval do Marcus

1. **Motor: whisper.cpp local em CPU.** É a recomendação central. A
   alternativa (API de nuvem, ~US$ 0,006/min [externo: preço OpenAI, não
   re-verificado]) custa centavos mas manda sua voz para fora da máquina e
   para de funcionar offline. Aprovar local-CPU é também aceitar o teste de
   latência do spike como critério de permanência.
2. **Modelo: small multilíngue oficial, `language: "pt"`, download no
   primeiro uso (~466 MB [externo: README whisper.cpp, não re-verificado]).**
   Alternativas: base (mais rápido, pt pior) se o small passar de ~3 s na
   sua máquina; medium descartado por ora (memória e latência). Fine-tune
   pt comunitário só com evidência de erro sistemático.
3. **Captura: `getUserMedia` no WebView2, sujeita ao spike.** Se o prompt de
   permissão do WebView2 se comportar mal dentro do Tauri, a branch 1 troca
   para `cpal` nativo sem mudar o resto do desenho. Você aprova a ordem de
   preferência, não o resultado do spike.
4. **Hotkey: qual combinação, e se a branch 3 entra na v1.1.** Sugestão
   inicial `Ctrl+Shift+Espaco` [suposição — colisões só aparecem no uso];
   registrável/trocável nas Configurações desde o primeiro dia. O corte
   mínimo (branches 1+2, só botão) fecha a v1.1 sem ela — decisão de
   escopo sua.
5. **Permissões novas:** nenhuma no capabilities para captura+motor via
   binding; a branch 3 adiciona `global-shortcut:*`; um eventual sidecar
   adicionaria entrada no escopo `shell`. Cada adição na mesma branch da
   feature, com rede de teste no molde de `instrucoes.escopo.test.ts`. No
   Windows, a chave de privacidade de microfone precisa estar ligada — a UI
   explica quando não estiver.
6. **Custo aceitável: R$ 0.** A recomendação inteira roda sem chave de API e
   sem assinatura. Se você quiser qualidade de nuvem depois, o teto de gasto
   é decisão sua nesse momento — não desta rodada.
7. **Fronteira com o tempo real:** a v1.1 é fala discreta sobre o
   `POST /comando`; conversa contínua com STT streamado fica para a fase do
   WebSocket, reaproveitando captura e motor. Aprovar esta fronteira evita
   que a v1.1 tente entregar a v2.
