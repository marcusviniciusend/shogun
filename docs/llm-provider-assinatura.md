# A assinatura de `LLMProvider.interpretar_comando` — opções, trade-offs e recomendação

> Documento de decisão, escrito **antes** de qualquer implementação. A
> recomendação explícita está na seção 7; o que ela ainda exige de aprovação
> humana está na seção 8. Nenhuma linha de código, contrato ou teste muda neste
> documento.
>
> Convenção de honestidade, usada no texto inteiro: **[projeto]** = fato
> verificado no código ou nos docs deste repositório nesta sessão;
> **[externo: fonte]** = leitura de documentação de terceiros, não exercitada
> aqui; **[suposição]** = estimativa ou expectativa, sem verificação. Nenhum
> número aparece sem uma dessas marcas.

---

## 1. O buraco

Dois documentos registram a **mesma** discussão em aberto e pedem que ela seja
resolvida junto:

- `docs/DESIGN.md`, passo 4, item 4 da lista final: *"**Assinatura estruturada
  do `LLMProvider`** — só se a concatenação do passo 4 não segurar"* [projeto];
- `docs/ROADMAP.md`, na seção de visão computacional: *"a interface
  `LLMProvider` hoje é `interpretar_comando(texto: str)`. Aceitar imagem muda
  essa assinatura, o que atinge os cinco provedores de uma vez (…) É a mesma
  discussão de assinatura registrada no passo 4 do DESIGN.md, e vale resolver
  as duas juntas."* [projeto]

A assinatura em questão, verbatim de `server/app/core/llm/base.py` [projeto]:

```python
async def interpretar_comando(self, texto: str) -> ComandoInterpretado: ...
```

Uma string entra, um objeto validado sai. Tudo o que o Shogun sabe fazer hoje
cabe nisso — e é exatamente por isso que a interface nunca mudou: o histórico
de conversa entrou **concatenado na string** (`core/llm/historico.py`),
deliberadamente, para não mexer nela [projeto].

O buraco não é que a assinatura esteja errada. É que **três** pressões
diferentes apontam para ela, ninguém decidiu se são a mesma decisão, e cada
documento registra um pedaço:

| # | Pressão | Onde está registrada | Estado |
|---|---|---|---|
| (1) | **Histórico estruturado** — trocar a string concatenada por lista de mensagens | `DESIGN.md` passo 4 | adiada com critérios de reabertura escritos |
| (2) | **Visão computacional** — aceitar imagem junto do texto | `ROADMAP.md`, "Ideias futuras" | ideia, **nenhuma frente iniciada** |
| (3) | **Streaming** — entrega incremental da fala | `streaming-design.md`, `shogun-wrapper-design.md` §§4–6 | desenho escolhido, implementação adiada |

O enunciado desta tarefa nomeia (2) e (3). **Mas o passo 4 do `DESIGN.md` — a
outra metade do "resolver as duas juntas" — é (1), não (3)** [projeto]. Essa
confusão de identidade é o primeiro achado deste documento, e a seção 3 mostra
que ela inverte o agrupamento: (1) e (2) são a mesma decisão; (3) é outra, e já
está tomada.

E há um quarto candidato que **não** é pressão: o STT. `stt-desktop-design.md`
§6 é categórico e a premissa está em `architecture.md` — o STT roda no cliente,
o servidor nunca recebe áudio, o texto transcrito entra no mesmo `POST /comando`
do texto digitado: *"nenhuma rota nova, nenhum campo novo, nenhuma mudança em
`shared/`, zero trabalho de servidor. O teste de paridade de contratos nem fica
sabendo."* [projeto] **O STT não pressiona a assinatura em nada** — ele produz
precisamente o `str` que ela já recebe. A única coisa do STT que toca este
assunto é a fronteira registrada em `shogun-wrapper-design.md` §7.5: a
*conversa contínua por WebSocket* é outro fluxo, fora da v1.1 [projeto]. Se um
dia áudio streamado chegar ao servidor, a discussão de assinatura reabre — mas
isso está explicitamente fora do corte, e não é o que está em cima da mesa.

## 2. O que já existe, e que qualquer opção deve reaproveitar

| Peça | Onde | Estado |
|---|---|---|
| `Protocol` `LLMProvider` (`nome`, `configurado`, `interpretar_comando`) | `core/llm/base.py` | pronto, `@runtime_checkable` |
| `SYSTEM_PROMPT` + `ESQUEMA_COMANDO` compartilhados | `core/llm/base.py` | prontos — identidade única entre provedores |
| `parsear_comando` (JSON → `ComandoInterpretado`, com descarte de nulos) | `core/llm/base.py` | pronto, usado pelos 4 corpos |
| `LLMIndisponivelError` como erro único de chamada | `core/llm/base.py` | pronto — é o gatilho do fallback |
| `ConfiguracaoInvalidaError` — falha de **configuração**, derruba o boot | `core/llm/base.py` | pronto (precedente: `OLLAMA_MODEL` ausente) |
| `PROVIDERS` + `criar_provider`/`montar_provider` | `core/llm/registry.py` | prontos; contrato uniforme de construtor (`Settings`) |
| `FallbackLLMProvider` — envolve a **chamada inteira** | `core/llm/fallback.py` | pronto |
| **Capacidade opcional fora do `Protocol` (`aquecer()`)** | `core/llm/aquecimento.py` | **pronto — é o precedente central deste documento** |
| Histórico concatenado (`montar_prompt`) | `core/llm/historico.py` | pronto; existe só para *não* mexer na assinatura |
| Único ponto de chamada em rota | `api/comando.py:249` | pronto |
| Rede de testes | `tests/test_llm.py` (68 testes), `tests/test_consumo.py`, `tests/conftest.py` | pronta |

Cinco propriedades do que existe condicionam todo o resto. As três primeiras
mudam a aritmética de custo que o `ROADMAP.md` registrou, e por isso vêm
primeiro.

**1. São cinco provedores, mas quatro corpos.** `PROVIDERS` tem cinco entradas
(`claude`, `deepseek`, `openai_mini`, `ollama`, `deterministico`) [projeto], mas
`deepseek` e `openai_mini` **compartilham** a implementação de
`interpretar_comando` em `OpenAICompatProvider` — cada subclasse só declara
credencial, modelo, endpoint e `response_format` [projeto]. As seis definições
de `async def interpretar_comando` em `server/app/` são: 4 provedores + 1 stub
do `Protocol` + 1 no `FallbackLLMProvider` [projeto]. A frase do `ROADMAP.md`
("atinge os cinco provedores de uma vez") descreve a superfície conceitual
corretamente, mas o trabalho de edição é **quatro corpos, e um deles atende dois
provedores de nuvem de uma vez**. Não é barato; é menos caro do que o registro
sugere.

**2. Não existe verificador de tipos no CI.** `.github/workflows/tests.yml` tem
dois jobs — `pytest` (3.11 e 3.13) e `vitest (desktop)` — e
`server/requirements-dev.txt` traz apenas `pytest` e `pytest-asyncio`
[projeto]. Não há `mypy`, `pyright` ou equivalente em lugar nenhum do
repositório [projeto]. Consequência direta: **nenhuma mudança de assinatura é
detectada estaticamente.** O que prende o contrato é execução de teste, e só.

**3. O teste que parece guardar a interface guarda só o nome do método.**
`test_todo_provedor_registrado_satisfaz_a_interface` faz
`assert isinstance(provider, LLMProvider)` contra o `Protocol`
`@runtime_checkable` [projeto]. Verificado experimentalmente nesta sessão: uma
classe cujo método tem assinatura completamente diferente **passa** nesse
`isinstance` [projeto] — `runtime_checkable` confere presença de atributo, não
forma. Somando com (2): um provedor que ignore silenciosamente um parâmetro novo
**não é pego por nada**. Essa é a mesma classe de falha que o `CLAUDE.md` nomeia
para o `ClientInstruction` — *"passa a mentir em silêncio"* [projeto] — e ela é
decisiva na comparação da seção 4.

**4. O `aquecer()` já resolveu "capacidade que nem todo provedor tem".** O
docstring de `core/llm/aquecimento.py` enuncia a doutrina inteira: *"O
aquecimento é OPCIONAL por provedor e fica fora do `Protocol` `LLMProvider` de
propósito: provedores de nuvem não têm o que aquecer, e exigir o método de todos
seria mudança de contrato sem benefício. Quem oferece aquecimento declara um
`async def aquecer()`; este módulo descobre por `getattr` e percorre o
`FallbackLLMProvider` para alcançar principal e reserva."* [projeto] Custo real
do precedente: **4 arquivos de `app/` tocados** (`aquecimento.py`, `ollama.py`,
`__init__.py`, `main.py`) e **7 funções de teste**, uma delas —
`test_aquecimento_ignora_provedor_sem_aquecer` — sendo exatamente o teste
"provedor sem a capacidade" [projeto]. Nenhum dos outros provedores foi tocado.

**5. O `FallbackLLMProvider` funciona porque envolve a chamada inteira.** Ele
repassa `texto` sem olhar, e o reserva refaz a chamada do zero [projeto]. Toda
opção abaixo precisa dizer o que ele faz com a informação nova — e a resposta
muda conforme a informação seja *um dado a mais* (imagem) ou *um modo de
entrega* (stream).

## 3. Pergunta 1 — uma migração só, ou separáveis?

**Separáveis. E o corte não é onde o enunciado supõe.**

As pressões agem em **eixos diferentes** da mesma função:

| Eixo | Pressões | O que muda |
|---|---|---|
| **Entrada** | (1) histórico estruturado, (2) visão | *o que entra* na chamada |
| **Saída** | (3) streaming | *como o resultado volta* |

O eixo da entrada é uma decisão só. Histórico estruturado e imagem pedem a mesma
coisa — que a chamada carregue mais do que uma string — e pagam o mesmo pedágio:
os 4 corpos, o fallback e as chamadas de teste. Fazer as duas em migrações
separadas é pagar esse pedágio **duas vezes**, e o segundo pagamento é gratuito
se o veículo escolhido na primeira for extensível (opção B da seção 4). É aqui,
e só aqui, que o *"vale resolver as duas juntas"* do `ROADMAP.md` se aplica.

O eixo da saída **já foi decidido, e a decisão foi não mexer nesta assinatura**.
`shogun-wrapper-design.md` §5 registra a conclusão de forma inequívoca: *"o
método de stream nasce **opcional** no `Protocol` (como `aquecer()`), o
`FallbackLLMProvider` ganha a variante streamada com a regra 'troca só antes do
primeiro chunk repassado', e o caminho não-streamado de todos os provedores fica
intacto — **nenhum dos cinco é reescrito**"* [projeto]. E `streaming-design.md`
§3(c) diz o mesmo pelo lado do custo: *"nenhuma mudança na interface
`LLMProvider` para quem não streama (método novo opcional, como foi o
`aquecer()`)"* [projeto].

Duas consequências que valem escrever com todas as letras:

- **O streaming não pressiona `interpretar_comando`. Ele adiciona um método
  irmão.** A pressão (3) do enunciado desta tarefa está, para efeito de
  assinatura, **encerrada** — falta implementar, não falta decidir.
- **O item do `ROADMAP.md` pode ser fechado pela metade agora.** Metade —
  streaming — está resolvida por documento mergeado; metade — entrada — continua
  aberta. Hoje as duas aparecem como uma pendência única e indistinta, o que faz
  o assunto parecer maior e mais travado do que é.

Há um único ponto em que os eixos se tocam, e ele é fraco: se a entrada virar um
objeto (opção B), o método streamado nasce recebendo **o mesmo** objeto, e não
uma segunda assinatura paralela que precisará ser migrada junto depois. Isso é
argumento para *que ordem seguir se as duas entrarem*, não para fundi-las numa
migração só. A ordem está na seção 7.

## 4. Pergunta 2 — as opções de assinatura

Todas partem do estado atual, `interpretar_comando(self, texto: str)`. O custo é
medido em: **4 corpos de provedor**, **1 stub de `Protocol`**, **1
`FallbackLLMProvider`**, **1 chamada de rota** (`api/comando.py:249`), **2
dublês de teste** (`conftest.py:63`, `test_llm.py:637`) e **48 linhas de
`tests/` que mencionam o método** [projeto].

### A. Parâmetro opcional com default

```python
async def interpretar_comando(
    self, texto: str, imagens: Sequence[Imagem] | None = None
) -> ComandoInterpretado: ...
```

- **Custo imediato:** o menor. As 48 linhas de teste e a chamada da rota
  **continuam compilando e passando sem tocar em nada** — é o que o default
  compra.
- **Custo real, e é onde ela se perde:** um provedor que simplesmente **não
  declare** o parâmetro novo continua passando no `isinstance` do
  `test_todo_provedor_registrado_satisfaz_a_interface` (propriedade 3 da seção
  2), e um que declare e **ignore** não é pego por absolutamente nada — não há
  verificador de tipos (propriedade 2). O modo de falha é silencioso: o Marcus
  manda um print, o `hermes3:8b` responde sobre o texto como se a imagem não
  existisse, e o comando retorna `status: ok`.
- **Custo acumulado:** aditivo por capacidade. A pressão seguinte acrescenta
  outro parâmetro opcional, e a assinatura vira uma lista de opcionais que cada
  corpo honra ou não, sem rede.
- **Fallback:** precisa repassar o parâmetro novo — uma linha. Mas ganha uma
  decisão nova e não trivial: repassar imagem para um reserva que não vê imagem
  é o caso da seção 5.

### B. Objeto de entrada

```python
class EntradaComando(BaseModel):
    texto: str
    historico: Sequence[Mensagem] = ()      # entra na migração (pressão 1)
    imagens: Sequence[Imagem] = ()          # entra quando a visão entrar (pressão 2)

async def interpretar_comando(self, entrada: EntradaComando) -> ComandoInterpretado: ...
```

- **Custo imediato:** o maior de uma vez só — 4 corpos, o stub, o fallback, a
  rota, os 2 dublês e as 48 linhas de teste, num único commit. Mas é **custo
  mecânico**: as chamadas viram `EntradaComando(texto=...)`.
- **Custo acumulado: zero.** É a **última** mudança de assinatura. Visão vira
  campo; qualquer pressão futura do eixo de entrada vira campo. Simetria exata
  com o que já existe na saída: `ComandoInterpretado` ganhou `uso` sem que
  ninguém mudasse assinatura nenhuma [projeto].
- **A virtude contraintuitiva:** **ela quebra alto**. Sem default, as 48 linhas
  de teste e os 2 dublês falham imediatamente se alguém esquecer um provedor —
  na ausência de verificador de tipos (propriedade 2), *quebrar* é a única
  forma de rede que este repositório tem. É o mesmo raciocínio do
  `test_paridade_contratos.py`, que o `CLAUDE.md` descreve como existindo *"para
  transformar o esquecimento em falha barulhenta"* [projeto].
- **Bônus estrutural:** `montar_prompt` some, e com ele some a gambiarra
  declarada de `historico.py` — o docstring do arquivo admite ser *"a opção que
  **não** mexe na interface"* [projeto]. O `SYSTEM_PROMPT` continua onde está;
  o `DESIGN.md` já previu esse desfecho para o passo 4.
- **Onde mora `EntradaComando`:** em `core/llm/base.py`, junto do
  `ComandoInterpretado` — é contrato **interno** de provedor, não contrato de
  fio. Não vai para `shared/` (seção 6).

### C. Método novo opcional, descoberto por `getattr` (o padrão `aquecer()`)

- **Para streaming: é a opção certa, e já foi escolhida** — seção 3. Streamar é
  uma **operação diferente** (transporte incremental) sobre a mesma
  interpretação; provedor que não sabe simplesmente não declara, e o
  `aquecimento.py` já demonstra o percurso do wrapper de fallback por `getattr`
  [projeto].
- **Para visão: é a opção errada, e vale dizer por quê.** Um
  `interpretar_comando_multimodal()` separado duplicaria, num segundo corpo por
  provedor, tudo o que o primeiro já faz — `SYSTEM_PROMPT`, `ESQUEMA_COMANDO`,
  `parsear_comando`, tradução de erro para `LLMIndisponivelError`, preenchimento
  de `UsoTokens` [projeto]. Visão não é operação diferente: é **a mesma
  operação com uma entrada a mais**. O critério que separa os dois casos —
  *operação nova* (aquecer, streamar) versus *entrada nova* (histórico, imagem)
  — é o que torna o precedente do `aquecer()` aplicável a um e não ao outro.
- **Custo se usada para visão:** baixo por provedor, alto no total, e com
  divergência garantida entre os dois corpos ao longo do tempo.

### D. Sobrecarga (`typing.overload` / união no primeiro parâmetro)

- Sem verificador de tipos no CI (propriedade 2), `@overload` é **comentário
  executável**: não impõe nada em tempo de execução e nada em CI [projeto].
- União no parâmetro (`str | EntradaComando`) entrega o pior dos dois mundos:
  cada um dos 4 corpos passa a ramificar por tipo de entrada, e a rota continua
  livre para mandar a forma antiga indefinidamente.
- **Desqualificada.** Não oferece nada que A não ofereça, e piora os corpos.

### Comparação

| | Custo imediato | Custo da capacidade seguinte | Falha silenciosa possível? | Fallback | Mata `montar_prompt` |
|---|---|---|---|---|---|
| A. Parâmetro opcional | **baixo** | baixo, mas repetido sempre | **sim** — nada detecta | +1 repasse | não |
| B. Objeto de entrada | **alto, uma vez** | **zero** (vira campo) | **não** — quebra alto | +1 repasse | **sim** |
| C. Método opcional | baixo | baixo | sim (silêncio por ausência) | percurso por `getattr` | não |
| D. Sobrecarga | médio | médio | **sim** | +1 repasse | não |

Custo do `FallbackLLMProvider` em A, B e D: **a mesma linha**. Ele repassa a
entrada, qualquer que seja a forma dela. O que muda de verdade no fallback não é
a assinatura — é a regra de capacidade da seção 5.

## 5. Pergunta 3 — provedor que não suporta a capacidade

O problema é concreto e o `ROADMAP.md` já o antecipou: *"o `hermes3:8b` local
ficaria de fora, tornando o fallback de nuvem obrigatório para comandos com
imagem"* [projeto]. Os candidatos locais listados no `server/README.md` são
todos de texto, e o próprio `ROADMAP.md` registra que *"os candidatos 8B atuais
de texto não processam imagem"* [projeto].

**Fato de partida, e é o que trava a discussão hoje: não existe declaração de
capacidade.** O `Protocol` expõe `nome`, `configurado` e `interpretar_comando`,
e nada mais [projeto]. `configurado` responde *"tem credencial?"*, não *"sabe
fazer o quê?"*. Sem uma declaração, o **único** sinal disponível é uma exceção
em tempo de chamada — ou seja, hoje a pergunta "quem decide?" não tem resposta
possível, porque ninguém tem a informação antes de tentar.

As quatro condutas possíveis:

### (i) Erro — levantar `LLMIndisponivelError`

- **Pró, e é sedutor:** custo de fiação **zero**. `LLMIndisponivelError` é
  exatamente o que o `FallbackLLMProvider` já intercepta [projeto] — o comando
  com imagem cairia no reserva de nuvem sem uma linha de código novo no wrapper.
- **Contra:** mente na semântica. O docstring diz que a exceção é *"O provedor
  de LLM não pôde ser consultado ou devolveu algo inválido"* [projeto] — mas o
  provedor **pôde** ser consultado; ele só não faz isso. Log e mensagem passam a
  descrever indisponibilidade onde há limitação.
- **Contra, pior:** se o reserva também não vê imagem — e o
  `deterministico` é justamente o reserva recomendado por *nunca falhar*
  [projeto] — o resultado é um **503 para um comando que tinha uma leitura de
  texto perfeitamente boa**. Fracasso total onde cabia fracasso parcial.
- Existe o erro certo para essa família: `ConfiguracaoInvalidaError`, que o
  próprio `base.py` descreve como *"não há o que tentar de novo nem para onde
  cair"* [projeto]. Mas ele derruba o boot, e "nenhum provedor vê imagem" só se
  torna um problema quando chega um comando com imagem — não no boot.

### (ii) Degradação silenciosa — ignorar a imagem e interpretar o texto

- **O pior desfecho possível, e o mais fácil de acontecer por acidente** (opção
  A da seção 4, propriedade 3 da seção 2). O Marcus mostra um print e pergunta
  "o que é esse erro?"; o modelo responde sobre um texto que, sozinho, não
  significa nada. O comando devolve `status: ok`.
- **Desqualificada.** Responder errado com confiança é pior do que não
  responder — é a mesma razão pela qual a opção D de `acao-resultado.md` foi
  desqualificada por *"ficar pior do que o problema"* [projeto].

### (iii) Degradação anunciada — interpretar o texto e dizer que não viu

- **Pró:** honesto, e não desperdiça a metade que dava para fazer.
- **Contra:** cada um dos 4 corpos passaria a redigir prosa dirigida ao usuário,
  e a identidade do Shogun é centralizada por princípio — *"trocar de LLM não
  pode mudar quem o Shogun é"* [projeto]. Exigiria uma string curada
  compartilhada, no molde dos `_DETALHE_*` de `api/comando.py` [projeto].
- **Contra:** a fala anunciada vai para `messages` e volta no `montar_prompt` do
  comando seguinte — o mesmo efeito colateral que `acao-resultado.md` analisou
  como o buraco (b) real daquele documento [projeto]. Tratável, mas é superfície
  a mais.

### (iv) Fallback obrigatório — escolher o provedor pela capacidade, antes de chamar

- **Pró:** é a única conduta que produz a resposta **certa** quando algum
  provedor configurado sabe ver.
- **Contra, se implementada na rota:** a rota passaria a saber quem sabe o quê,
  e hoje ela não sabe **nada** sobre implementação — depende da interface e
  recebe o provedor por injeção [projeto]. Seria regressão de arquitetura.
- **Sem contra, se implementada no lugar certo:** o `FallbackLLMProvider` já é
  o componente cujo ofício é escolher entre dois provedores. Generalizar a
  regra dele de *"troca quando o principal falha"* para *"troca quando o
  principal falha **ou** não declara a capacidade que a entrada exige"* mantém a
  rota tão ignorante quanto é hoje.

### Recomendação desta seção: **o provedor declara, o fallback roteia, a rota
não fica sabendo**

Concretamente, e em ordem de dependência:

1. **`Protocol` ganha uma declaração de capacidade** — na forma de uma
   propriedade ao lado de `configurado` (por exemplo
   `capacidades: frozenset[str]`, com um default que significa "só texto", para
   que nenhum provedor existente precise mudar). Seria a primeira coisa que o
   `Protocol` ganha desde `configurado`, e por isso é decisão de arquitetura, não
   de implementação (seção 8).
2. **O `FallbackLLMProvider` roteia por capacidade antes de chamar** — se o
   principal não declara o que a entrada exige, o reserva assume **sem** o
   principal ser chamado. Isso é mais barato e mais honesto do que a conduta (i),
   e não gasta um round-trip para descobrir o que já se sabia.
3. **Se nenhum provedor configurado tem a capacidade, a conduta é (iii),
   anunciada e curada num só lugar** — resposta de texto, mais uma frase estável
   dizendo que a imagem não foi olhada. Nunca (ii). Um 503 aqui (conduta i) é
   desproporcional: o comando tinha metade utilizável.

**Quem decide, em uma linha:** o **provedor** declara o que sabe; o **fallback**
escolhe; a **rota** continua ignorante; e o **Marcus** decide a política — porque
"fallback de nuvem obrigatório para comando com imagem" não é decisão técnica
(seção 8).

Três consequências dessa política que precisam estar na mesa antes de ela ser
aprovada, e nenhuma delas é técnica:

- **Custo.** Comando com imagem passa a ser sempre pago, mesmo num setup
  local-first. `GET /consumo` mostraria isso, o que é bom; mas a escolha de
  gastar é do Marcus.
- **Privacidade.** Comando com imagem **sai da máquina obrigatoriamente**. Numa
  instalação cujo modelo principal é local, é uma inversão de expectativa — e
  prints de tela são a frente 2 da visão computacional no `ROADMAP.md`
  [projeto], isto é, o conteúdo mais sensível dos três.
- **Saída viável.** Um modelo local multimodal (o `ROADMAP.md` cita LLaVA e
  Llama 3.2 Vision [projeto]) evitaria as duas. Mas `stt-desktop-design.md`
  mede a máquina: RTX 4050 Laptop, 6 GB de VRAM, dos quais o `hermes3:8b` já
  ocupa ~4,7 GB de pesos mais ~1 GB de contexto — **sobram ~0,3 GB** [projeto].
  Rodar visão local hoje significa **trocar** o modelo principal, não somar um.

## 6. Pergunta 4 — impacto em `shared/` e nos testes

### `shared/` — depende da pressão, e a resposta é diferente para cada uma

`CommandRequest` é hoje `{session_id, text, client}` e `CommandResponse` é
`{session_id, text, actions}` [projeto].

| Pressão | Muda `shared/`? | Por quê |
|---|---|---|
| (1) Histórico estruturado | **não** | o histórico é lido do banco **dentro do servidor** (`api/comando.py`, antes da chamada) [projeto]. Nunca trafegou no fio; continua sem trafegar. |
| (2) Visão | **sim, inevitavelmente** | a imagem vem do cliente. Não há como entrar sem campo novo em `CommandRequest`. |
| (3) Streaming | **provavelmente não** | por desenho: `shogun-wrapper-design.md` §4 estabelece que `event: final` carrega *"o `CommandResponse` completo, idêntico ao que o `POST /comando` devolve hoje"* [projeto]. Os payloads de `status`/`chunk`/`erro`/`done` são pequenos e podem entrar como contratos novos **ou** ficar fora — decisão da branch de streaming, não desta. |

E `EntradaComando` (opção B) **não** vai para `shared/`: é contrato entre a rota
e os provedores, interno ao servidor. Confundir os dois criaria um contrato de
fio para algo que nenhum cliente vê.

Quando a visão entrar, valem as regras que o `CLAUDE.md` já impõe, sem exceção:
as duas pontas de `shared/` na mesma branch, de preferência no mesmo commit, sob
pena de `test_paridade_contratos.py` quebrar o CI [projeto]. E há uma decisão de
fio embutida que não é deste documento mas precisa ser lembrada: **como a imagem
trafega** (base64 no JSON, upload separado, referência) — com efeito direto em
tamanho de corpo, rate limit e no que vai parar em log.

### Os testes que prendem o contrato hoje

| O que prende | Onde | O que pega — e o que não pega |
|---|---|---|
| `assert isinstance(provider, LLMProvider)` para os 5 registrados | `test_llm.py:582` | pega **nome de método ausente**. **Não pega assinatura** — verificado nesta sessão [projeto] |
| 48 linhas de `tests/` que chamam `interpretar_comando` posicionalmente | `test_llm.py` (44), `test_consumo.py` (5, menos a def), `conftest.py` | pegam mudança **sem default**; **não pegam** parâmetro opcional |
| 2 dublês que implementam o método | `conftest.py:63`, `test_llm.py:637` | precisam ser atualizados na opção B |
| Contrato de **saída** | `test_llm.py:90` (`test_schema_e_fechado_em_todos_os_objetos`) e os testes de structured output por provedor | intactos em qualquer opção — nenhuma delas mexe em `ESQUEMA_COMANDO` |
| Precedente de capacidade opcional | 7 testes de aquecimento, incl. `test_aquecimento_ignora_provedor_sem_aquecer` | é o molde pronto para testar "provedor sem a capacidade" |

Baseline verificada nesta sessão, neste worktree: **257 testes passando no
servidor** [projeto] — o mesmo número que o `ROADMAP.md` registra para `dev`
[projeto].

A leitura desta tabela é uma só, e é o argumento central da recomendação:
**a rede que existe só pega a opção B.** A opção A foi desenhada para não
quebrar nada, e num repositório sem verificador de tipos "não quebrar nada" e
"não ser verificado por nada" são a mesma frase.

Uma lacuna a registrar para quem implementar, seja qual for a opção: se
`capacidades` entrar no `Protocol` (seção 5), ela nasce com o mesmo problema do
`ClientInstruction` — **uma declaração que nenhum tipo obriga ninguém a honrar**.
Um provedor pode declarar que vê imagem e ignorá-la. A rede análoga existe e tem
nome no repositório: `test_invariantes_contrato.py` e
`test_provedores_sem_uso_esta_em_dia` (este último transforma exatamente esse
tipo de esquecimento em falha, para `PROVEDORES_SEM_REGISTRO_DE_USO`) [projeto].
Capacidade nova precisa nascer com rede equivalente, no mesmo commit.

## 7. Recomendação

**Não migrar agora. Fatiar, e disparar a primeira fatia junto com a primeira
feature que precise dela — que será a visão, não o streaming.**

Em ordem de peso:

1. **Nenhuma das duas features tem data, e uma delas talvez nunca entre.** A
   visão é "ideia futura", com as três frentes marcadas **"nenhuma iniciada"**
   [projeto]. O streaming está decidido para depois da v1.0 e **condicionado**:
   *"se a espera medida incomodar no uso diário"* [projeto], contra uma mediana
   medida de 4,1 s para respostas de 1–3 frases [projeto]. Migrar assinatura
   agora é pagar hoje, com risco de regressão nos 4 corpos, por duas features
   que podem não entrar. É literalmente o raciocínio que o passo 4 do
   `DESIGN.md` já aplicou uma vez, com o mesmo argumento, e que produziu o
   `historico.py` [projeto].

2. **O streaming não precisa da migração — e isso fecha metade do item
   agora, de graça.** Seção 3. `shogun-wrapper-design.md` §5 já decidiu que o
   stream nasce como método opcional e que **nenhum dos cinco provedores é
   reescrito** [projeto]. O que resta é de documentação: hoje `ROADMAP.md` e
   `DESIGN.md` passo 4 apresentam a discussão como um bloco só e em aberto, o
   que a faz parecer maior do que é. **Ressalva de escopo:** essa correção não
   é feita aqui — este documento não altera outros, e `ROADMAP.md` está sendo
   mexido por outro agente nesta rodada. Fica como achado para o coordenador.

3. **Quando a visão entrar, ir direto ao objeto de entrada (B), e levar o
   histórico estruturado na mesma migração.** Os 4 corpos são tocados de
   qualquer jeito; o que se escolhe é tocá-los **uma vez** ou **uma vez por
   capacidade**. E num repositório sem verificador de tipos, B é a única opção
   cuja falha é barulhenta (seções 4 e 6). A opção A economiza uma tarde e
   compra um modo de falha silencioso permanente.

4. **A migração não fica mais cara por esperar** — mesmo argumento que
   `streaming-design.md` usa para a opção (c) [projeto]. Nada do que existe
   hoje precisa ser desfeito: `montar_prompt` é deletado na fatia 1, não
   refeito; `ESQUEMA_COMANDO`, `parsear_comando` e `SYSTEM_PROMPT` ficam
   intocados em todas as fatias.

### A ordem, se e quando entrar

Cada fatia é mergeável sozinha, com a suíte verde, no molde que
`streaming-design.md` §5 já usa [projeto]:

| # | Fatia | Toca | Comportamento observável |
|---|---|---|---|
| 1 | `EntradaComando` com `texto` + `historico`; 4 corpos, `Protocol`, fallback, rota, 2 dublês, 48 linhas de teste. `montar_prompt` morre. | só `server/` | **idêntico** se o histórico continuar concatenado dentro dos corpos; **muda** se já virar lista de mensagens nas APIs — decidir na branch (ver seção 8) |
| 2 | `capacidades` no `Protocol` + roteamento por capacidade no `FallbackLLMProvider` + rede mecânica da declaração | só `server/` | nenhum (ninguém declara capacidade além de texto ainda) |
| 3 | Campo de imagem nos **dois** `shared/`, rota, e os provedores que veem | `shared/` + `server/` + desktop | visão funcionando |

Fatia 1 sozinha já paga: mata a gambiarra declarada do `historico.py` e resolve
o passo 4 do `DESIGN.md` no mérito. **Ela é a única que faz sentido considerar
antes da visão** — se o critério de reabertura do passo 4 disparar (o modelo
confundir quem falou o quê, responder ao histórico em vez do comando, ou o
modelo local degradar mais que os de nuvem no mesmo histórico [projeto]),
fatia 1 entra por mérito próprio e as fatias 2 e 3 ficam mais baratas de graça.

**Gatilhos para reabrir esta decisão** (qualquer um basta):

- a visão computacional deixa de ser ideia e vira branch aprovada — **é o
  gatilho principal**;
- qualquer critério do passo 4 do `DESIGN.md` disparar no uso real;
- um modelo local multimodal caber na máquina (hoje sobram ~0,3 GB de VRAM
  [projeto]) — o que muda a resposta da seção 5 inteira, porque o fallback de
  nuvem deixaria de ser obrigatório;
- áudio streamado passar a chegar ao servidor (a fase WebSocket que
  `stt-desktop-design.md` §6 põe explicitamente fora do corte [projeto]).

## 8. O que **não** está decidido aqui

Tudo abaixo é de arquitetura ou de coordenação, e precisa de aval antes de
qualquer implementação:

1. **A decisão principal: migrar agora ou fatiar quando a primeira feature
   entrar.** A recomendação é **fatiar, disparado pela visão** (seção 7).
   "Não fazer agora" é a resposta honesta para uma assinatura pressionada por
   duas features sem data — mas a chamada é do Marcus.
2. **Considerar a metade do streaming encerrada para efeito de assinatura?** A
   leitura deste documento é que sim, por decisão já mergeada
   (`shogun-wrapper-design.md` §5). Se o Marcus concordar, o `ROADMAP.md` (linha
   ~176) e o passo 4 do `DESIGN.md` merecem a correção — **por outro agente,
   fora desta branch**.
3. **Objeto de entrada (B) ou parâmetro opcional (A), quando entrar.** A
   recomendação é **B**, e o argumento decisivo não é elegância: é que a rede
   deste repositório só pega B (seções 4 e 6). C está certa para streaming e
   errada para visão; D está desqualificada.
4. **A conduta para provedor sem a capacidade** — erro, degradação silenciosa,
   degradação anunciada ou fallback obrigatório. A recomendação é
   **declaração + roteamento no fallback + degradação anunciada como último
   recurso**, nunca silêncio (seção 5).
5. **A política de imagem: fallback de nuvem obrigatório, sim ou não.** Não é
   decisão técnica — é custo (todo comando com imagem é pago) e **privacidade**
   (a imagem sai da máquina obrigatoriamente, inclusive prints de tela). Num
   setup local-first é inversão de expectativa, e merece ser escolhida de
   propósito.
6. **`capacidades` entra no `Protocol`?** Seria o primeiro acréscimo à interface
   desde `configurado`. Se entrar, nasce com a mesma doença do
   `ClientInstruction` — declaração que nenhum tipo obriga a honrar — e precisa
   de rede mecânica no mesmo commit, no molde de
   `test_provedores_sem_uso_esta_em_dia` (seção 6).
7. **O histórico estruturado viaja junto com a migração da visão?** A
   recomendação é **sim** — é o momento barato. Mas é uma mudança de
   **qualidade** (como o modelo lê a conversa) pegando carona numa mudança
   **estrutural**, e se a qualidade regredir vai ser difícil saber qual metade
   causou. Alternativa conservadora: fatia 1 move o histórico para dentro do
   objeto **mantendo a concatenação nos corpos**, e a troca para lista de
   mensagens vira uma fatia própria, isolada e reversível. Recomendo a
   conservadora se a fatia 1 entrar sozinha; a combinada se as três entrarem em
   sequência.
8. **Como a imagem trafega no fio** — base64 no `CommandRequest`, upload
   separado ou referência. Afeta tamanho de corpo, rate limit (`comando`,
   20/min [projeto]) e o que vai para log. É decisão de contrato, do
   **agente-contratos**, e não foi tratada aqui.
9. **Adotar um verificador de tipos no CI antes de migrar assinatura?** Este
   documento não pediu a pergunta, mas a levantou: hoje **nada** verifica
   assinatura no repositório (seção 2, propriedades 2 e 3). Um `mypy` mesmo
   frouxo sobre `server/app/core/llm/` mudaria a comparação da seção 4 — com
   ele, a opção A deixa de ter modo de falha silencioso e volta a ser
   competitiva. É a única coisa neste documento que vale considerar fazer
   **antes** de qualquer das outras, e é decisão de infraestrutura, não desta
   área.
10. **Divisão de trabalho.** `Protocol`, `EntradaComando` e `shared/` são do
    **agente-contratos**; os 4 corpos, o `FallbackLLMProvider` e a rota são do
    **agente-backend**; enviar imagem e consumir SSE é do **agente-desktop**.
    Três áreas para uma migração — se ela entrar, a divisão é da coordenação.

---

### Verificações que ficaram em aberto

Registradas para não passarem por verificadas:

- **Como cada API aceita imagem** (formato do bloco de conteúdo, limites de
  tamanho, custo em tokens de imagem) não foi verificado nesta sessão
  [suposição] — nenhuma chamada a API real foi feita, conforme a norma do
  projeto. Quando a fatia 3 abrir, isso precisa ser confirmado provedor a
  provedor, do mesmo jeito que `streaming-design.md` deixou marcado
  "verificar" para deepseek e Ollama [projeto].
- **Se algum modelo local multimodal cabe nos ~0,3 GB de folga** [projeto] não
  foi testado — a aritmética da seção 5 vem da leitura de
  `stt-desktop-design.md` e do `server/README.md`, não de medição nova
  [suposição].
- **Nenhum número de latência ou qualidade** aparece neste documento além dos
  que `streaming-design.md` §2 já mediu e publicou [projeto].
