# Roteamento por complexidade e revisão de custo — opções, trade-offs e recomendação

> Documento de decisão, escrito **antes** de qualquer implementação. Nenhuma
> linha de código, contrato, migração ou variável de ambiente muda aqui. A
> recomendação explícita está na seção 8; o que ela exige de aprovação humana
> está na seção 9.
>
> Data: 2026-09-13 · agente-backend · responde ao item de backlog de
> `.maestri/proximas-rodadas.md`: *"Roteamento por complexidade / revisão de
> custo — o `GET /consumo` agora precifica Opus corretamente; avaliar se
> comandos curtos justificam Opus ou se um modelo menor basta."*

## Convenção de marcação

Este documento mistura três tipos de afirmação, e a diferença importa mais aqui
do que em outros documentos porque o item de backlog pede um número:

- **[F]** — **fato verificado**: lido no código deste repositório nesta branch
  (a partir de `8cbd9df`). Reproduzível abrindo o arquivo citado.
- **[E]** — **leitura externa**: documentação da API da Anthropic via a
  referência local `claude-api` (cache de 2026-06-24). Confiável, mas não
  verificada contra a API viva — e preço e suporte de parâmetro mudam por
  decisão comercial do fornecedor, não por release do Shogun.
- **[S]** — **suposição declarada**: hipótese minha, com o valor escolhido
  explicitado. Nenhuma conclusão desta página depende de uma **[S]** sozinha.

Onde falta dado, o documento diz que falta em vez de estimar. Isso acontece uma
vez, e é a parte mais importante da seção 4.

---

## 1. O buraco — e o que o item de backlog mistura

O item pergunta se **"comandos curtos justificam Opus"**. A pergunta pressupõe
que o trabalho do LLM no Shogun varia em dificuldade, e que existe uma fatia
fácil que poderia ir para um modelo menor.

Lendo o código, a pressuposição não se sustenta do jeito que está escrita — mas
existe uma assimetria real, e ela é **por ação, não por comprimento**:

**[F]** A rota `POST /comando` (`server/app/api/comando.py`) **descarta a
`resposta_falada` do modelo em duas das três ações**. O fluxo é literalmente:

```python
resposta = intencao.resposta_falada
if intencao.acao == "consultar_pendencias":
    resposta, acao = await _consultar_pendencias(intencao, pendencias)  # sobrescreve
elif intencao.acao == "abrir_app":
    resposta, acao = _abrir_app(intencao)                               # sobrescreve
```

Em `consultar_pendencias` a fala final é montada pelo servidor a partir das
pendências ordenadas; em `abrir_app` é uma frase fixa com o nome do app. A prosa
que o Opus escreveu nesses dois casos é gerada, cobrada e jogada fora.

Ou seja: **para duas das três ações, o modelo é um classificador de três rótulos
mais dois parâmetros opcionais (`app`, `limite`) — não um redator.** Só em
`conversar` a qualidade da escrita chega ao Marcus.

Essa é a assimetria que justificaria roteamento. Mas ela tem um problema de
ordem que é o núcleo deste documento: **saber que o comando é `abrir_app` é o
resultado da chamada, não a entrada dela.** Rotear "comandos de ação para o
modelo barato" exige decidir a ação antes de perguntá-la ao modelo. É a seção 3.

Uma segunda leitura do item: *"revisão de custo"* não precisa de roteador
nenhum. `SHOGUN_MODEL` é uma variável de ambiente **[F]** (`core/config.py`,
default `claude-opus-5`). Trocar o modelo para um mais barato é uma decisão de
uma linha de `.env` que atinge 100% dos comandos — e captura a maior parte do
ganho que um roteador capturaria, sem nenhuma das complicações das seções 5 e 6.
As duas metades do item têm custo de implementação separados por duas ordens de
grandeza, e a barata não é a que dá nome ao item.

---

## 2. O que o código faz hoje — a base factual

Tudo nesta seção é **[F]**.

| Peça | Onde | O que é relevante para roteamento |
|---|---|---|
| `LLMProvider` | `core/llm/base.py` | `Protocol` de um método: `async interpretar_comando(texto) -> ComandoInterpretado`. Um roteador cabe nessa assinatura sem mudá-la. |
| `SYSTEM_PROMPT` + `ESQUEMA_COMANDO` | `core/llm/base.py` | Compartilhados por todos os provedores. 237 e 1.114 caracteres (JSON compacto), respectivamente — medidos em 2026-09-19, depois de a semântica das ações passar a ser derivada de `SEMANTICA_ACOES`. A `DICA_ESQUEMA`, que só deepseek e ollama recebem, soma outros 653. |
| `PROVIDERS` | `core/llm/registry.py` | `claude`, `deepseek`, `openai_mini`, `ollama`, `deterministico`. Todo provedor recebe `Settings` no construtor. |
| `montar_provider` | `core/llm/registry.py` | Monta o principal e o embrulha em `FallbackLLMProvider`. Roda **uma vez** — está atrás de `@lru_cache(maxsize=1)`. |
| `FallbackLLMProvider` | `core/llm/fallback.py` | Só entra em ação em `LLMIndisponivelError`. Preserva o `uso.provider` de quem de fato respondeu. |
| `DeterministicoProvider` | `core/llm/deterministico.py` | Interpreta por palavra-chave, sem rede e sem credencial. `configurado` é sempre `True`. Nunca levanta `LLMIndisponivelError`. |
| `ClaudeProvider` | `core/llm/claude.py` | Usa `output_config={"effort": "low", "format": {"type": "json_schema", ...}}` e `model=config.shogun_model`. |
| `PRECOS` | `core/llm/precos.py` | `claude` 5,00/25,00 · `deepseek` 0,28/0,42 · `openai_mini` 0,15/0,60 · `ollama` 0/0 (USD por 1M de tokens). Provedor fora da tabela custa zero. |
| `MessageUso` | `db/models.py` | Colunas: `message_id`, `provider`, `input_tokens`, `output_tokens`, `created_at`. **Não há coluna de ação.** |
| `consumo_por_provider` | `db/repositorio.py` | Agrega tokens **por provedor** num período. Não há corte por ação, porque não há o dado. |
| `_resumir_fallback` | `api/consumo.py` | Compara os provedores do banco contra **um** `principal_configurado` e **uma** `reserva_configurada`, lidos do ambiente de agora. |
| `montar_prompt` | `core/llm/historico.py` | Concatena até `SHOGUN_HISTORICO_MAX_MENSAGENS` (default 20) mensagens **antes** do comando atual, tudo numa string só. |

Dois fatos negativos que valem tanto quanto os positivos:

- **[F] Não há prompt caching em lugar nenhum do servidor.** `cache_control` não
  aparece no código. E **[E]** o prefixo mínimo cacheável da Anthropic é da ordem
  de 1024 tokens; o prefixo estável do Shogun (`SYSTEM_PROMPT` + schema = 1.351
  caracteres, ≈ 350 tokens) fica bem abaixo disso. **Cache de prompt não é uma
  alavanca disponível neste desenho** — não por esquecimento, por tamanho. O
  número cresceu em 2026-09-19 (era 1.135) e a conclusão não se mexeu: a margem
  para o piso é de quase 3×.
- **[F] O custo por comando cresce com a sessão, não com a dificuldade.** O termo
  que domina o input é o bloco de histórico (até 20 mensagens reenviadas a cada
  comando), e ele é idêntico para "bom dia" e para uma pergunta difícil. Se o
  objetivo é custo, a janela de histórico é uma alavanca maior que a escolha de
  modelo — e mais barata de mexer.

---

## 3. Dá para classificar a complexidade antes de chamar o LLM? (pergunta 1)

**Resposta curta: dá para classificar *intenção* sem pagar chamada, e o código
para isso já existe. Mas a confiabilidade dele nunca foi medida, e como está
escrito ele tem dois defeitos que só aparecem no papel de roteador.**

### 3.1 O teto lógico

Qualquer classificador que custe uma chamada de LLM está fora por construção: o
trabalho inteiro do Shogun por comando **é** uma chamada pequena de LLM. Pagar
uma chamada para decidir quem paga a próxima chamada não economiza — no melhor
caso troca um Opus por um barato **mais** um barato. Isso elimina de saída o
desenho "um modelo pequeno classifica e um grande responde".

Sobra roteamento por **regra local**: zero rede, zero token, latência
desprezível. É exatamente o que o `DeterministicoProvider` faz.

### 3.2 O `DeterministicoProvider` como roteador — o que ele realmente entrega

**[F]** Ele decide em três ramos, sobre o texto normalizado (minúsculas, sem
acentos):

1. qualquer uma de 7 palavras-chave (`pendencia`, `pendente`, `tarefa`,
   `afazer`, `o que falta`, `to-do`, `todo list`) → `consultar_pendencias`;
2. o regex `\b(?:abra|abre|abrir|inicie|iniciar)\s+(?:o|a|os|as)?\s*(?P<app>.+)$`
   → `abrir_app` com o resto da linha como nome do app;
3. **qualquer outra coisa** → `conversar`, com uma fala fixa de "estou no modo
   determinístico".

O ramo 3 é a raiz do problema. **Ele não é um julgamento, é um resto.** Como
fallback final isso é correto e deliberado — o provedor existe para sempre
responder alguma coisa. Como roteador, é a diferença entre *"isto é uma
conversa"* e *"não faço ideia"*, e um roteador precisa distinguir as duas: a
primeira pode ir para o modelo barato, a segunda não pode ir para lugar nenhum
sem supervisão.

Reaproveitá-lo como roteador não é reaproveitar a classe, é **escrever uma
função diferente**: uma que devolve três valores (`pendências` / `abrir_app` /
`não sei`) em vez de dois mais um resto. O `_normalizar`, as palavras-chave e o
regex se reaproveitam; a decisão, não.

### 3.3 Dois defeitos que hoje não custam nada e no papel de roteador custariam

**[F] Defeito 1 — a varredura de palavra-chave roda sobre o histórico inteiro.**
A rota chama `llm.interpretar_comando(montar_prompt(historico, texto))`, ou seja,
o provedor recebe o bloco de histórico concatenado com o comando. O teste do
determinístico é `any(chave in normalizado for chave in _CHAVES_PENDENCIAS)` —
sobre a string inteira. Uma sessão em que o Marcus tenha dito "tarefa" vinte
mensagens atrás faz **todo** comando seguinte cair em `consultar_pendencias`.

Hoje isso é praticamente inofensivo: o determinístico só roda como reserva
final, num cenário em que a nuvem e o modelo local caíram juntos. Como roteador,
rodaria em 100% dos comandos, e o falso positivo cresceria com o tamanho da
sessão. **[F]** Nenhum teste exercita o determinístico com um prompt de
histórico — os testes de `tests/test_llm.py` passam frases nuas, e `montar_prompt`
não aparece nesse arquivo.

(O regex do `abrir_app` escapa disso por acidente feliz: `.` não casa `\n` e `$`
fica no fim da string, então ele só enxerga a última linha, que é o comando
atual.)

**[F] Defeito 2 — o regex de `abrir_app` é ganancioso e não valida o alvo.**
`.+$` captura tudo até o fim da linha, sem nenhuma noção do que é um app.
"abre a janela", "abrir mão disso", "abre o jogo" viram `abrir_app` com nome
inventado. E o servidor **não pode** validar contra um catálogo: o mapa de apps é
deliberadamente do cliente, em tempo de build (ver
[`mapa-apps-configuravel.md`](mapa-apps-configuravel.md), trava 2) — o servidor
só sabe recusar `:`, `/` e `\` (`_APP_PROIBIDO`). Um roteador baseado nesse regex
não tem como se auto-limitar aos casos que ele acerta.

### 3.4 Com que confiabilidade, então?

**Não se sabe, e essa é a resposta honesta.** Não existe conjunto rotulado de
comandos reais do Marcus com a ação correta anotada. Os testes unitários do
determinístico usam frases escolhidas a dedo por quem escreveu as regras — eles
provam que o código faz o que o autor quis, não que o que o autor quis acerta o
que o Marcus fala.

Há um caminho barato para obter esse dado, e ele não exige código novo nem
migração — está na seção 8, passo 0.

---

## 4. O ganho real de custo (pergunta 2)

### 4.1 O que dá para afirmar com exatidão

Com a tabela de `precos.py` **[F]** e a tabela de preços da Anthropic **[E]**
(Opus 5 US$ 5,00/25,00 · Sonnet 5 US$ 3,00/15,00 · Haiku 4.5 US$ 1,00/5,00 por
1M de tokens), sai um resultado limpo:

> **A razão de preço entre esses modelos é a mesma no input e no output.**
> Opus → Haiku 4.5 é exatamente 5× em ambos; Opus → Sonnet 5 é exatamente 5/3.

Consequência que importa: **a fração economizada não depende da mistura
input/output.** Não é preciso saber quantos tokens de prompt versus resposta o
Shogun gasta para afirmar:

| Troca | Economia por comando roteado |
|---|---|
| Opus 5 → Sonnet 5 | exatamente **40%** |
| Opus 5 → Haiku 4.5 | exatamente **80%** |
| Opus 5 → `ollama` (local) | **100%** do custo de API |
| Opus 5 → `deterministico` | **100%** (nenhuma chamada) |

Confirmação de saúde do PR #48: **[F]** a linha `claude` de `precos.py` está em
5,00/25,00 e **[E]** esse é o preço do `claude-opus-5`, que é o default de
`shogun_model` **[F]**. O comentário do arquivo e o modelo em uso batem. O item
de backlog está certo ao dizer que "o `GET /consumo` agora precifica Opus
corretamente".

### 4.2 O que **não** dá para afirmar — e por quê

**A fração é exata. O valor absoluto não existe, e sem ele a decisão não fecha.**
Três lacunas, todas verificadas:

1. **[F] `messages_uso` não sabe qual ação foi executada.** As colunas são
   `message_id`, `provider`, `input_tokens`, `output_tokens`, `created_at`, e
   `consumo_por_provider` agrupa só por `provider`. Não existe consulta possível
   hoje que responda *"que fatia do gasto veio de `conversar`"* — que é
   precisamente a fatia **não** roteável (seção 1). Sem esse corte, o ganho de um
   roteador por ação é indeterminado entre 0% e ~100% do gasto.
2. **[F] O `deterministico` nunca grava uso** (`PROVEDORES_SEM_REGISTRO_DE_USO`).
   Se um roteador mandar comandos para ele, esses comandos somem do `/consumo`.
   A economia fica invisível pelo mesmo instrumento que motivou o item.
3. **Não há amostra de produção do `claude`.** `streaming-design.md` §2 registra,
   sobre a amostra de `shogun.db` de 2026-09-05 a 2026-09-08 (95 mensagens, 46
   pares): *"não há amostra identificada do claude — a fileira de baixo é só
   ollama"*. Não consegui consultar o banco nesta sessão (a leitura de
   `server/shogun.db` foi bloqueada pela política do ambiente), então **não tenho
   número novo para oferecer e não vou inventar um**. O que resolve isso não é
   uma medição nova: é rodar `GET /consumo` sem parâmetros depois de uso real —
   ele já devolve `custo_real_usd` e o `comparativo` provedor a provedor, que é
   literalmente a resposta da pergunta "quanto custaria se fosse tudo de outro
   provedor".

### 4.3 A ordem de grandeza, com as hipóteses na mesa

Como a decisão depende de *quanto dinheiro está em jogo*, segue a aritmética
paramétrica. **Os preços são [F]/[E]; os volumes de token são [S] declarados; as
contas são contas.**

**[S]** Faixas escolhidas: input de 500 a 2.000 tokens por comando (o prefixo
estável é pequeno — ~1.184 caracteres **[F]** — e o que varia é o bloco de até 20
mensagens de histórico); output de 100 a 300 tokens. O limite inferior de output
vem do que está medido: `streaming-design.md` §2 registra **43–127 tokens de
saída** naquela amostra. O limite superior de 300 existe porque **[E]** o Opus 5
tem thinking adaptativo ligado por padrão e os tokens de raciocínio são cobrados
como output — a amostra medida é de um modelo local 8B sem thinking, e não serve
de proxy para o Opus nessa dimensão.

**USD por 1.000 comandos:**

| input / output | Opus 5 | Sonnet 5 | Haiku 4.5 |
|---|---|---|---|
| 500 / 100 | 5,00 | 3,00 | 1,00 |
| 500 / 300 | 10,00 | 6,00 | 2,00 |
| 1.000 / 100 | 7,50 | 4,50 | 1,50 |
| 1.000 / 300 | 12,50 | 7,50 | 2,50 |
| 2.000 / 100 | 12,50 | 7,50 | 2,50 |
| 2.000 / 300 | 17,50 | 10,50 | 3,50 |

E 1.000 comandos são quanto tempo? **[S] derivado de [F]**: 46 pares em 4 dias de
calendário na amostra de `streaming-design.md` dá ~11 a 15 comandos por dia, ou
seja, **1.000 comandos ≈ 2 a 3 meses** de uso naquele ritmo.

**A leitura:** no ritmo medido e sob as hipóteses acima, o Shogun rodando 100%
em Opus custa **algo entre US$ 5 e US$ 18 por trimestre**. Um roteador perfeito
— que acertasse toda vez e mandasse tudo que é roteável para o modelo mais
barato — economizaria uma fração disso.

A ressalva que impede tratar esse número como definitivo: aquela amostra é de um
período de testes, majoritariamente `ollama`. Uso diário real pode ser 10× maior,
e aí a conta vira US$ 50–180 por trimestre. É por isso que a recomendação da
seção 8 vem com **gatilho numérico** em vez de com uma conclusão fixa: o número
que decide é o `custo_real_usd` de um mês real, e ele já é obtenível sem escrever
uma linha de código.

Duas alavancas descartadas de passagem, para não voltarem como sugestão:
**[E]** a Batch API roda a 50% do preço mas é assíncrona — incompatível com um
assistente de voz; e o cache de prompt está fora por tamanho de prefixo (§2).

---

## 5. Onde o roteamento moraria sem quebrar o desenho (pergunta 3)

Quatro lugares possíveis. Dois estão tecnicamente desqualificados, e é bom
registrar por quê.

### (A) Um `LLMProvider` que roteia — **o único lugar que cabe**

Uma classe que implementa o mesmo `Protocol`, recebe os provedores candidatos no
construtor e escolhe um por comando. Exatamente a forma do `FallbackLLMProvider`
**[F]**: um provedor que não fala com API nenhuma, só compõe outros.

- A assinatura não muda, então **nenhuma rota muda** — a regra de dependência do
  `CLAUDE.md` continua intacta.
- `uso.provider` continua sendo o nome de quem de fato respondeu **[F]**, então o
  `por_provider` do `/consumo` permanece verdadeiro sem nenhuma mudança.
- Entra no registro como qualquer outro, ou é montado em `montar_provider`.
- Compõe com o fallback nos dois sentidos (roteador por fora, fallbacks por
  dentro; ou o contrário) — com consequências diferentes, seção 6.

Custo: uma classe nova, a política de roteamento em `Settings`, testes, e o
conserto do `/consumo` descrito em 6.3. Estimativa **[S]**: 2 branches.

### (B) A factory (`montar_provider` / `criar_provider`) — **desqualificada**

**[F]** `montar_provider` roda uma vez: `_provider_cacheado` é
`@lru_cache(maxsize=1)` e `get_llm_provider` devolve sempre a mesma instância.
Roteamento é uma decisão **por comando**; a factory é código de boot. Ela pode
*montar* o roteador — deve, inclusive — mas não pode *ser* o roteador sem virar
uma factory por request, o que é uma mudança de desenho bem maior que a feature.

### (C) A rota (`comando.py`) — **desqualificada**

Colocaria política de escolha de modelo na camada HTTP e faria a rota conhecer
provedores concretos. É a violação direta da regra do `CLAUDE.md` ("a rota
depende da interface, nunca de uma implementação concreta"), pela conveniência
de não escrever uma classe.

### (D) Nenhum dos dois — trocar `SHOGUN_MODEL` — **a opção que o item esconde**

**[F]** `ClaudeProvider` lê `model=self._config.shogun_model`. Apontar para um
modelo mais barato é `.env`, não código, e atinge 100% dos comandos.

Uma armadilha verificada, e ela é específica:

> **[F]** `ClaudeProvider` manda `output_config={"effort": "low", ...}` em toda
> requisição. **[E]** O parâmetro `effort` **não é aceito pelo Haiku 4.5** — é
> um modelo de geração anterior, e a chamada volta erro. No Shogun, um erro da
> Anthropic vira `LLMIndisponivelError` **[F]**, que aciona o fallback. Ou seja:
> `SHOGUN_MODEL=claude-haiku-4-5` hoje faria **todo** comando falhar no
> principal e ser atendido pelo reserva, em silêncio — o servidor continuaria
> respondendo, e o único sinal seria a `taxa` do bloco `fallback` do `/consumo`
> ir a 1,0.
>
> **Sonnet 5 não tem esse problema: [E]** ele aceita `effort` de `low` a `max`.
> `SHOGUN_MODEL=claude-sonnet-5` é, de fato, uma troca de zero linhas.

**[E]** Os dois modelos suportam structured output (`output_config.format` com
`json_schema`), então o `ESQUEMA_COMANDO` continua imposto pela API em ambos —
nada muda no `parsear_comando`.

Marcado como **[E]** de propósito: antes de mergear qualquer coisa que dependa
disso, a primeira chamada real contra a API confirma ou desmente em segundos.

---

## 6. Risco de degradar a resposta, e como o `FallbackLLMProvider` interage (pergunta 4)

### 6.1 O erro de roteamento é silencioso — e é isso que o diferencia de tudo que já medimos

Esta é a objeção mais forte a um roteador, e ela é estrutural.

**[F]** O `FallbackLLMProvider` só reage a `LLMIndisponivelError`. E a
`CONTEXTO-GERAL.md` §4.2 registra por que isso virou uma métrica boa: *"cada
acionamento é um JSON fora do schema"* — um modelo ruim erra o **formato**, o
formato é validado, a falha é barulhenta, e desde o PR #48 ela é um número no
`/consumo`.

Um roteador quebra essa cadeia inteira:

- **Um modelo barato que devolve JSON válido com a ação errada não levanta
  exceção nenhuma.** O `parsear_comando` aprova, a rota executa, o Marcus ouve
  "Você tem 3 pendências" quando perguntou outra coisa. **O `FallbackLLMProvider`
  não protege a decisão de roteamento** — ele protege contra indisponibilidade,
  e um erro de roteamento não é indisponibilidade.
- **Uma fala pior não é um erro.** Em `conversar` — a única ação em que a prosa
  chega ao Marcus (§1) — a degradação é de qualidade, e não existe nenhum sinal
  no sistema que a capture. Não há coluna, log, métrica ou teste que diga "esta
  resposta deveria ter ido para o Opus".

Resumindo a assimetria: **hoje, escolher mal o modelo produz um erro contável;
com roteador, escolher mal o modelo produz uma resposta pior e nenhum dado.**

### 6.2 Ordem de composição com o fallback

Os dois arranjos funcionam e têm falhas diferentes:

- **Roteador por fora, cada candidato com seu fallback**: a resiliência por rota
  fica preservada, mas há N pares (principal, reserva) e o conceito de "o
  principal" deixa de existir — ver 6.3.
- **Fallback por fora, roteador como principal**: um único reserva cobre
  qualquer rota que falhe. Mais simples, mas o reserva provavelmente é caro (ou é
  o `deterministico`, que não grava uso), então a economia vaza toda vez que o
  fallback dispara.

Em ambos, **[F]** `aquecer_provider` precisaria aprender a atravessar o roteador:
hoje `_componentes` desfaz recursivamente só o `FallbackLLMProvider`. Um roteador
com um `ollama` dentro não seria aquecido no startup, e o "primeiro comando frio"
que o PR #23 resolveu voltaria pela porta dos fundos. É uma linha de código, mas
é uma linha que só se descobre lendo `aquecimento.py`.

### 6.3 O roteador estraga o instrumento que motivou o item

**[F]** `_resumir_fallback` (`api/consumo.py`) deriva a taxa comparando os
provedores encontrados no banco contra **um** `principal_configurado`
(`SHOGUN_LLM_PROVIDER`) e **uma** `reserva_configurada`. Com um roteador, não
existe *um* principal: existem N rotas. Toda mensagem atendida por uma rota que
não seja o `SHOGUN_LLM_PROVIDER` cairia em `mensagens_outros`, que **[F]** é
documentado como *"o sinal de que a configuração mudou no meio da janela"*.

Ou seja: o bloco passaria a acusar divergência de configuração em regime normal,
e `taxa` viraria ruído. O `GET /consumo`, que o item de backlog cita como o que
tornou a discussão possível, é a primeira vítima do roteador — e consertá-lo é
pré-requisito, não acabamento.

### 6.4 O risco que **não** existe

Vale dizer o que está protegido, para a lista de riscos ser honesta: **[F]** o
`ESQUEMA_COMANDO` é fechado e validado em `parsear_comando` no fim de todo
caminho, e a invariante de segurança do `abrir_app` (`_APP_PROIBIDO`) roda na
rota, depois de qualquer provedor. **Nenhum roteador consegue afrouxar o
contrato nem a barreira de segurança** — o pior que um modelo barato faz é
escolher a ação errada dentro do conjunto válido. Isso é uma boa notícia real: o
risco é de qualidade, não de correção nem de segurança.

---

## 7. As opções, lado a lado

| | (A) Roteador `LLMProvider` | (D1) `SHOGUN_MODEL=claude-sonnet-5` | (D2) `SHOGUN_MODEL=claude-haiku-4-5` | (E) Não fazer agora |
|---|---|---|---|---|
| Economia por comando afetado | até 100% (rotas para local/determinístico) | **exatos 40%** | **exatos 80%** | 0 |
| Comandos afetados | só os classificáveis | **todos** | **todos** | — |
| Custo de implementação | ~2 branches + conserto do `/consumo` | **zero linhas** (`.env`) | ~1 branch pequeno (`effort` condicional) | zero |
| Reversível por `.env`? | não (código novo) | **sim, na hora** | sim, depois do branch | — |
| Risco de degradar a resposta | alto e **invisível** (§6.1) | uniforme e observável (um modelo só) | idem, maior | nenhum |
| Efeito no `/consumo` | **quebra `_resumir_fallback`** (§6.3) | nenhum | nenhum | nenhum |
| Efeito no `FallbackLLMProvider` | precisa repensar o par | nenhum | nenhum se `effort` for corrigido; **fallback permanente** se não for | nenhum |
| Precisa de dado que não temos? | **sim** (§4.2) | não | não | não |

---

## 8. Recomendação

**Não construir o roteador agora. Fazer a medição (passo 0), e tratar a "revisão
de custo" como o que ela é — uma troca de variável de ambiente, não uma
feature.**

O raciocínio, sem rodeio:

- **O item pede um roteador por complexidade, e a complexidade não é o eixo.** O
  eixo real é a ação (§1), e a ação é o resultado da chamada, não a entrada
  dela. Rotear por ação exige adivinhá-la antes, e o único adivinhador gratuito
  que temos nunca teve a acurácia medida e tem dois defeitos que só aparecem
  nesse papel (§3.3).
- **A opção barata captura a maior parte do ganho.** Sonnet 5 economiza exatos
  40% de tudo por zero linha de código, é reversível na hora e não toca em
  instrumento nenhum. Um roteador perfeito economizaria mais, mas só sobre a
  fatia roteável — e **[F]** não sabemos qual é essa fatia.
- **O dinheiro em jogo provavelmente não paga a engenharia.** Sob as hipóteses
  declaradas (§4.3), o ritmo medido dá US$ 5–18 por trimestre em Opus. Duas
  branches de roteador para economizar uma fração disso é troca ruim — e a conta
  fica pior quando se soma o conserto do `/consumo` (§6.3).
- **O roteador degrada em silêncio, e é o único mecanismo do projeto que faria
  isso.** Todo o resto do desenho do LLM converge para "falha vira erro contável"
  (§6.1). Um roteador é a primeira peça que trocaria erro barulhento por
  qualidade pior sem registro.
- **Não fazer agora não encarece fazer depois.** O lugar certo (A) continua
  existindo, o `Protocol` não muda, e nenhuma das trocas de `SHOGUN_MODEL`
  precisa ser desfeita para o roteador entrar.

### Ordem de implementação, se e quando valer

**Passo 0 — medir, custo ~zero, faz sentido mesmo que nada mais entre.** Duas
coisas, nenhuma exige código novo:

1. rodar `GET /consumo` sem parâmetros depois de uma semana de uso real em
   Opus — `custo_real_usd` responde "quanto dói" e `comparativo` responde
   "quanto doeria em cada provedor", que é a pergunta do item de backlog
   respondida pelo endpoint que já existe;
2. obter a fatia por ação **sem migração**: as falas de `consultar_pendencias` e
   `abrir_app` são montadas pelo servidor a partir de moldes fixos **[F]**
   ("Você tem N pendência(s):", "Nenhuma pendência registrada, Marcus.", "Pedi
   para este aparelho abrir o X, Marcus.", e as frases de recusa). Uma consulta
   de leitura sobre `messages` classifica retroativamente as respostas do
   assistente por molde, e o que não casar com molde nenhum é `conversar`. Isso
   dá a divisão que falta em §4.2 a partir do banco que já existe.

**Passo 1 — se o custo incomodar:** `SHOGUN_MODEL=claude-sonnet-5` no `.env`,
com `SHOGUN_LLM_FALLBACK_PROVIDER` como está. Zero código, −40% exatos, reversão
imediata. Rodar uma semana e comparar a `taxa` de fallback antes e depois — se
subir, o Sonnet está errando o schema e a troca se pagou em dinheiro e se perdeu
em qualidade; se ficar igual, a troca é de graça.

**Passo 2 — se ainda incomodar:** tornar o `effort` condicional ao modelo em
`ClaudeProvider` (só manda quando o modelo aceita) e testar
`SHOGUN_MODEL=claude-haiku-4-5`. Uma branch pequena e bem contida. **Confirmar
antes [E]**: que o Haiku 4.5 de fato recusa `effort`, e que aceita
`output_config.format`.

**Passo 3 — só se 1 e 2 não bastarem e o volume tiver crescido muito:** o
roteador como opção (A), precedido pelo conserto de `_resumir_fallback` (§6.3) e
pela medição de acurácia do classificador (§3.4) sobre os dados do passo 0. Sem
esses dois pré-requisitos, é construir no escuro.

**Nunca:** roteamento na rota (C) ou na factory (B).

### Gatilhos para reabrir esta decisão

Qualquer um basta:

- o `custo_real_usd` de um mês real passar do que o Marcus considere irrelevante
  — o número é dele, não meu; como referência, os passos 1 e 2 se pagam com
  folga a partir de alguns dólares por mês, e o passo 3 não se paga tão cedo;
- o passo 0.2 mostrar que `conversar` é uma fatia pequena do volume — aí a fatia
  roteável é grande e o roteador muda de figura;
- o Shogun ganhar ações caras de verdade (visão computacional está no backlog, e
  imagem no prompt é outra ordem de grandeza de input) — aí a diferença entre
  comandos deixa de ser cosmética e "roteamento por complexidade" passa a
  descrever algo real;
- o `agents/` sair do `if/elif` para dez ações (**[F]** `CONTEXTO-GERAL.md`
  §4.5) — mais ações significam mais fatia não-conversacional.

---

## 9. O que **não** está decidido aqui

Tudo abaixo precisa de aval antes de qualquer implementação:

1. **A decisão principal.** A recomendação é **medir (passo 0) e trocar
   `SHOGUN_MODEL` se doer (passo 1)**, sem roteador. "Não fazer agora" é a
   conclusão honesta — mas a chamada é do Marcus.
2. **Qual é o limiar de custo que incomoda.** É o número que decide os passos 1,
   2 e 3, e é uma decisão de produto, não de engenharia. Sem ele, este documento
   entrega frações exatas e nenhum veredito sobre valor absoluto.
3. **Se o Shogun pode falar com uma voz diferente.** Trocar de modelo muda o
   estilo da fala em `conversar`, mesmo com o `SYSTEM_PROMPT` idêntico. O
   `CONTEXTO-GERAL.md` §2.4 diz que *"a identidade do Shogun não pode depender do
   fornecedor"* — isso foi escrito sobre o contrato, não sobre o timbre. Se o
   timbre também for inegociável, os passos 1 e 2 mudam de natureza.
4. **Se vale reduzir `SHOGUN_HISTORICO_MAX_MENSAGENS`.** É a alavanca de custo
   mais barata que existe (§2) e está fora do escopo deste item, mas atacar custo
   sem mencioná-la seria omissão. Mexer nela troca dinheiro por memória de
   conversa — decisão de produto.
5. **Se os dois defeitos do `DeterministicoProvider` (§3.3) viram correção
   própria.** Hoje eles quase não custam, porque o provedor só roda como reserva
   final. Corrigir a varredura de palavra-chave para olhar só o comando atual é
   pequeno e independente desta decisão — mas é mudança de comportamento de um
   provedor, e não cabe ser feita de passagem.
6. **Confirmar as afirmações [E] contra a API viva** antes de mergear qualquer
   coisa que dependa delas: preço de Sonnet 5 e Haiku 4.5, recusa de `effort` no
   Haiku 4.5, e suporte a `output_config.format` nos dois. São minutos de
   verificação e derrubam ou confirmam o passo 2 inteiro.
7. **Uma defasagem pequena, notada de passagem e não corrigida nesta branch:** o
   comentário de `shogun_llm_provider` em `core/config.py` lista
   `claude | deepseek | openai_mini | ollama` e **[F]** não menciona o
   `deterministico`, que está em `PROVIDERS` desde que virou o fallback final.
   Uma linha, mas em arquivo que não é a entrega desta rodada.
