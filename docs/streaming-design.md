# Streaming — documento de decisão

Data: 2026-09-08 · agente-backend · **sem código: é material para decisão do
Marcus.** Cobre os passos 6 e 7 do [DESIGN.md](DESIGN.md), último item técnico
da lista v1.0.

---

## 1. O problema

Hoje a resposta do `/comando` é um `CommandResponse` único: o cliente espera em
silêncio até a interpretação inteira terminar, e só então ouve a voz. O
[DESIGN.md](DESIGN.md) marca a entrega incremental (passo 6, SSE/WebSocket) e o
TTS conforme chega (passo 7) como 🔴 novos, e registra a tensão exata que trava
os dois:

> os provedores usam saída estruturada (JSON schema fechado), e a fala é um
> *campo* desse JSON. Não dá para streamar `resposta_falada` token a token sem
> uma das duas saídas — (a) parsing incremental do JSON parcial, ou (b) duas
> chamadas, uma que decide a ação e outra que gera a fala em texto puro.

Em outras palavras: o formato que garante ação certa (`acao` + `parametros` +
`resposta_falada`, validado por schema) é o mesmo formato que impede a fala de
sair antes do JSON fechar. Streamar JSON pela metade não é parseável; esperar o
JSON inteiro é não streamar.

Duas consequências que o DESIGN.md também já registra e que qualquer opção
precisa respeitar:

- as `actions` só existem **depois** da interpretação completa — o que se
  streama é a fala, nunca as ações;
- o TTS precisa de fronteiras faláveis (frase/oração), não de tokens soltos
  (passo 7).

Um fato do código atual que muda o tabuleiro e não estava registrado no
DESIGN.md: **o `ESQUEMA_COMANDO` já emite `resposta_falada` por último.** A
ordem das propriedades no schema (`acao`, `parametros`, `resposta_falada`) é a
ordem em que os provedores geram os tokens — tanto no structured output das
APIs de nuvem quanto na gramática do Ollama. Ou seja: o envelope da ação chega
nos primeiros tokens do stream, e o resto do stream é quase todo o conteúdo da
string da fala. A tensão "JSON não streama" é menor do que parece: **o único
campo que interessa streamar é exatamente o sufixo do JSON.**

E um segundo fato: quando a ação é `consultar_pendencias` (ou `abrir_app`), a
fala final **não vem do LLM** — é montada pelo servidor a partir dos dados (ou
delegada ao cliente). Streaming da geração do LLM só beneficia `conversar`.
Para as ações, o ganho viria só de anunciar a ação mais cedo.

## 2. O custo real de hoje — medido

Fonte: `shogun.db` de uso real (95 mensagens, 46 pares usuário→assistente,
2026-09-05 a 2026-09-08). Metodologia: diferença entre `created_at` da mensagem
do usuário e da resposta do assistente — é a espera de ponta a ponta do lado do
servidor (LLM + execução de ação), que é o que o Marcus sente, mas **não**
separa tempo-até-primeiro-token de tempo de geração. Limitações honestas: o
`provider` só passou a ser gravado com o rastreamento de consumo (#21), então
34 pares antigos aparecem sem provedor (mistura de testes com claude e ollama);
**não há amostra identificada do claude** — a fileira de baixo é só ollama.

| Amostra | n | mediana | mín | máx |
| --- | --- | --- | --- | --- |
| ollama local (hermes3:8b, aquecido) | 12 | **4,1 s** | 2,5 s | 8,5 s |
| sem provedor identificado (mistura, pré-#21) | 34 | 6,1 s | 1,1 s | 13,0 s |

Dois números derivados que importam mais que a mediana:

- **As respostas são curtas: 43–127 tokens de saída** (1 a 3 frases faladas).
  Não existe "resposta longa chegando aos poucos" no uso real do Shogun hoje —
  o streaming encurtaria uma espera de ~4 s para talvez ~2 s até a primeira
  frase falável, não transformaria uma espera de 30 s em fluidez.
- O pior caso medido (13 s) veio da fase de testes com modelo frio/nuvem — o
  caso "primeiro comando frio" já foi eliminado pelo aquecimento no startup
  (#23), e o retry único do desktop (#22) cobre o resíduo.

O que **não** foi medido e a implementação precisaria confirmar: o
tempo-até-primeiro-token isolado (exigiria instrumentar o provedor) e qualquer
número do claude em uso real.

## 3. As opções

### (a) Não streamar na v1.0 — fechar o corte sem os passos 6 e 7

Declarar a v1.0 completa sem entrega incremental; o pacote inteiro (resposta +
TTS completo) continua como está.

- **Pró:** custo zero; nenhum risco novo; os números medidos dizem que a espera
  típica é ~4 s para 1–3 frases — desconfortável, não quebrada. O TTS que
  acabou de entrar fala a resposta completa e funciona.
- **Pró:** nenhuma das outras opções fica mais difícil depois — nada do que
  existe hoje precisa ser desfeito para streamar na v1.1.
- **Contra:** a espera em silêncio continua; a percepção de "assistente lento"
  não melhora. O DESIGN.md fica com dois passos abertos indefinidamente.
- **Custo:** 0 branches (só atualizar DESIGN.md/ROADMAP registrando a decisão).

### (b) Duas fases — envelope estruturado + fala streamada em texto puro

Primeira chamada devolve só `{acao, parametros}` (JSON curto); se a ação for
`conversar`, uma segunda geração produz a fala em texto puro, streamada por SSE.

- **Pró:** a fala vira texto livre — streaming trivial, sem parsing de JSON
  parcial; o TTS consome frases limpas.
- **Contra:** **dobra chamadas e latência de arranque** no caminho mais comum
  (`conversar`): paga-se um round-trip inteiro (e o time-to-first-token do
  modelo, que é a parte cara) duas vezes. No modelo local de 8B, é pagar duas
  vezes o custo de prefill do prompt com histórico.
- **Contra:** duas chamadas = dois pontos de falha e um estado intermediário
  novo no fallback (interpretou no principal, falou pelo reserva? a
  personalidade da fala muda no meio do comando).
- **Contra:** custo em dinheiro dobra nos provedores pagos (o prompt com
  histórico é reenviado).
- **Custo:** ~4 branches — método novo no `LLMProvider` (gerar fala em texto),
  os 5 provedores + fallback, rota SSE, cliente desktop + TTS incremental.

### (c) Streaming do campo final — parsear incrementalmente aproveitando a ordem do schema

Uma chamada só, streamada. O servidor consome o stream do provedor com um
scanner incremental que: (1) lê o prefixo até fechar `acao`/`parametros` (os
primeiros ~15–30 tokens, porque o schema os emite primeiro); (2) daí em diante,
extrai o conteúdo da string `resposta_falada` conforme gera, repassando por SSE
em fronteiras de frase; (3) no fim, valida o JSON completo com o
`parsear_comando` de sempre — o parse final é a rede de segurança, o
incremental é só transporte.

É a variante concreta do "streaming especulativo": especula-se pouco, porque a
gramática (Ollama) e o schema fechado (nuvem) tornam a forma do prefixo
previsível; a única correção possível no fim é descartar/completar a última
frase se a validação final divergir.

- **Pró:** uma chamada só — custo e latência de arranque idênticos aos de hoje;
  nenhuma mudança na interface `LLMProvider` para quem não streama (método novo
  opcional, como foi o `aquecer()`).
- **Pró:** o envelope chega nos primeiros tokens: a ação pode ser anunciada/
  despachada cedo mesmo quando a fala nem começou.
- **Pró:** degrada bem: provedor sem suporte a stream (ou `deterministico`) usa
  o caminho atual e o SSE entrega um evento único — o cliente não distingue.
- **Contra:** o scanner incremental de JSON é código novo e sutil (escapes
  dentro da string, unicode, chunks cortando tokens no meio). Mitigação real: a
  string `resposta_falada` é o último campo, então o scanner precisa entender
  só "prefixo até o campo" + "conteúdo de string JSON" — não um parser de JSON
  genérico.
- **Contra:** fallback só é limpo **antes do primeiro token repassado** ao
  cliente. Falha no meio do stream, com fala já dita pelo TTS, não tem como
  trocar de provedor silenciosamente — vira erro para o cliente tratar.
- **Custo:** ~3 branches — (1) scanner incremental + método opcional de stream
  nos provedores que suportam (começando por 1–2), com fallback intacto no
  caminho não-streamado; (2) rota SSE nova (`POST /comando` continua existindo
  como está — cliente escolhe); (3) desktop consumindo SSE + TTS por frase.

### (d) Mudar o contrato — fala fora do JSON via saída nativa por provedor

Reestruturar para o mecanismo nativo de cada API separar dados estruturados de
texto: por exemplo, tool use no Claude (a ação como chamada de ferramenta, a
fala como texto livre do turno) e equivalentes nos demais.

O que cada provedor suporta **hoje** (confiança indicada — verificar na
implementação o que estiver marcado):

| Provedor | Structured output + streaming hoje | Confiança |
| --- | --- | --- |
| claude (API Anthropic) | Streaming SSE nativo; `output_config.format` streama o JSON como deltas de texto; tool use streama argumentos (`input_json_delta`), com `eager_input_streaming: true` por ferramenta para streaming fino **sem beta**. Suporta o desenho "ação = tool call, fala = texto do turno". | alta (referência local de 2026) |
| openai_mini | `response_format` json_schema strict + `stream: true` convivem; JSON chega como deltas. Tool calls também streamam argumentos. | alta |
| deepseek | JSON mode + stream funcionam juntos (deltas), **sem** enforcement de schema — a fala fora do JSON até ajudaria, mas o suporte a tool use streaming é o ponto a verificar. | média — verificar |
| ollama | `/api/chat` com `format` (schema→gramática) + `stream: true` convivem: os tokens saem restringidos pela gramática, streamados. Tool use existe, mas modelos 8B degradam mais em tool use do que em JSON por gramática. | média — verificar na versão instalada |
| deterministico | Sem geração: responde inteiro, instantâneo. Qualquer desenho precisa aceitar "stream de um evento só". | alta (é nosso) |

- **Pró:** é o desenho "certo" das APIs modernas: dados são dados, texto é
  texto; o streaming da fala vira o caso trivial de streaming de texto.
- **Contra:** é a opção mais cara e mais arriscada: muda `SYSTEM_PROMPT`/
  `ESQUEMA_COMANDO` (a identidade compartilhada dos provedores), os **5**
  provedores, o `FallbackLLMProvider` e todos os testes de uma vez — a mesma
  classe de mudança que o DESIGN.md (passo 4) decidiu adiar até haver sinal de
  necessidade.
- **Contra:** heterogêneo entre provedores: tool use streaming é maduro no
  claude/openai, incerto no deepseek e frágil no modelo 8B local — o Shogun
  ficaria com qualidade de interpretação diferente por provedor, que é
  exatamente o que a arquitetura atual evita.
- **Custo:** ~4–5 branches, com risco de regressão na ação (o campo mais
  importante) para melhorar a entrega do campo menos crítico.

## 4. Impacto transversal

| Dimensão | (a) nada | (b) duas fases | (c) campo final | (d) contrato novo |
| --- | --- | --- | --- | --- |
| 5 provedores | intactos | +1 método em todos | +1 método opcional (começa em 1–2) | todos reescritos |
| `FallbackLLMProvider` | intacto | estado intermediário novo | limpo até o 1º token; depois, erro | reescrito |
| TTS (entrou agora) | fala completo (como está) | fala por frase | fala por frase | fala por frase |
| Clientes | intactos | SSE novo | SSE novo (rota atual continua) | SSE novo + contrato novo |
| Custo por comando | igual | ~2x no `conversar` | igual | igual |
| Risco de regressão na ação | zero | baixo | baixo (parse final continua validando) | **alto** |

Nota sobre o TTS em qualquer opção com streaming: "falar conforme chega" exige
agregação por frase no cliente (ou no servidor, entregando eventos já em
fronteira de frase — mais simples para os dois clientes consumirem igual). Com
respostas de 1–3 frases, o ganho é começar a falar após a primeira frase
(~1–2 s antes), não um fluxo contínuo longo.

## 5. Recomendação

**Fechar a v1.0 sem streaming (opção a), e registrar a opção (c) como o
desenho escolhido para quando streaming entrar** — como primeiro item técnico
pós-v1.0, se a espera medida incomodar no uso diário.

Fundamentos, na ordem que pesa:

1. **Os números não justificam segurar a v1.0.** Espera mediana de ~4 s para
   respostas de 1–3 frases, com o pior caso estrutural (comando frio) já
   eliminado por outra via. Streaming melhora ~2 s de percepção no caminho
   `conversar`; não muda `consultar_pendencias` nem `abrir_app`, cuja fala nem
   vem do LLM.
2. **A opção (c) não fica mais cara por esperar.** Não exige desfazer nada de
   hoje: a ordem do schema já favorece o campo final, a rota atual continua
   existindo, e o método de stream nasce opcional como o `aquecer()`. Decidir
   (c) agora e implementar depois custa o mesmo que implementar agora.
3. **(b) e (d) têm contras estruturais, não de cronograma** — (b) dobra custo e
   cria estado intermediário no fallback; (d) arrisca o campo que não pode
   regredir (a ação) e quebra a homogeneidade entre provedores. Não os
   recomendo nem agora nem depois, salvo se a implementação de (c) revelar que
   o scanner incremental é pior do que estimado.

Incertezas declaradas: não há medição de claude em uso real nem de
time-to-first-token isolado; o suporte streaming+schema do deepseek e da versão
instalada do Ollama está marcado como "verificar". Nenhuma delas muda a
recomendação (a), porque (a) não depende de provedor — mas todas precisam ser
confirmadas no primeiro branch de (c).

Esforço estimado se/quando (c) entrar: 3 branches (scanner + provedor,
rota SSE, desktop+TTS), cada um mergeável sozinho, com o comportamento atual
preservado até o último.
