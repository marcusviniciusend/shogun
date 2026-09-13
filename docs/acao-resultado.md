# `POST /acao-resultado` — opções, trade-offs e recomendação

> Documento de decisão, escrito **antes** de qualquer implementação. A
> recomendação explícita está na seção 8; o que ela ainda exige de aprovação
> humana está na seção 9. Nenhuma linha de código, contrato ou rota muda neste
> documento.

## 1. O buraco

A ação `abrir_app` não é executada pelo servidor. `_abrir_app`
(`server/app/api/comando.py`) monta uma `ClientInstruction` e a entrega dentro
da `AgentAction`; quem abre o app é o cliente. O contrato já registra a
consequência, nas docstrings dos dois `shared/`:

> Com instruction preenchida, `status: "ok"` significa DELEGAÇÃO FEITA, não app
> aberto (…) Divergência aceitável na v1; um eventual `POST /acao-resultado` é
> extensão futura, não pendência deste contrato.

O servidor nunca fica sabendo o desfecho. Isso não é **um** buraco — são três,
de tamanhos muito diferentes, e tratá-los como um só é o que faz a extensão
parecer mais valiosa do que é:

**(a) O `status` mente por convenção.** `ok` = delegação feita. Está escrito no
contrato, os dois clientes sabem, e nenhum consumidor hoje interpreta `ok` como
"abriu". Custo prático: **zero**. É divergência documentada, não bug.

**(b) O histórico registra uma fala que o usuário não ouviu.** Este é real.
`processar_comando` chama `_fechar_conversa(repo, session_id, resposta, …)` com
`resposta` = o `text` da resposta — sempre. Mas a regra de consumo do contrato
manda o cliente falar `fallback_text` **em vez de** `text` quando a execução
falha. Então, no caminho de falha:

| | O que existe |
|---|---|
| O que o usuário viu e ouviu | "Não consegui abrir o Spotify neste aparelho, Marcus." |
| O que `messages` guardou | "Pedi para este aparelho abrir o Spotify, Marcus." |

E `messages` não é um log morto: é a fonte de `GET /sessoes/{id}/mensagens` (o
histórico que o desktop reexibe) **e** do `montar_prompt` do comando seguinte.
Ou seja, o LLM é informado de que o pedido foi feito e aparentemente deu certo.
Se o Marcus emendar "não abriu, tenta de novo", o modelo está lendo um contexto
que o contradiz.

**(c) Não há telemetria de qual app falha.** O mapa curado do desktop tem
quatro entradas (`navegador`, `explorer`, `calculadora`, `spotify`) mais um
punhado de sinônimos. Todo nome fora dele cai no `fallback_text`, e o servidor
não sabe quais nomes são. Isso interessa a um item que já está no backlog
("mapa de apps configurável") — mas hoje o dado existe: está no `console.warn`
do cliente, a um F12 de distância.

Vale notar o que **não** é buraco: desde o PR #41, `app` com `:`, `/` ou `\` é
**recusado antes de virar instrução** (`_APP_PROIBIDO`). Esses casos devolvem
`status: "error"` e `instruction: null` — nunca geram instrução, logo nunca
geram resultado. O endpoint de resultado só diz respeito a instruções que
efetivamente saíram no fio.

## 2. O que já existe, e que qualquer opção deve reaproveitar

| Peça | Onde | Estado |
|---|---|---|
| `ClientInstruction` (`type`, `app`, `fallback_text`) | `shared/python/__init__.py` + `shared/ts/index.ts` | pronto, com teste de paridade no CI |
| `AgentAction.instruction` + a anotação da extensão futura | os dois `shared/` | pronto |
| Delegação e redação do `fallback_text` | `api/comando.py::_abrir_app` | pronto |
| **O ponto exato que conhece o desfecho** | `desktop/src/lib/instrucoes.ts::executarInstrucoes` | pronto |
| Log local da causa da falha | `console.warn` / `console.error` em `instrucoes.ts` | pronto |
| Autenticação Bearer por token fixo | `core/security.py` | pronta |
| Rate limit por token, baldes `comando` e `leitura` | `core/rate_limit.py` | pronto (**não há balde de escrita**) |
| `registrar_assistente` / tabela `messages` | `db/repositorio.py`, `db/models.py` | prontos |
| `messages_uso` — precedente de "tabela satélite de `messages`" | `db/models.py` | pronto |
| Rede mecânica do contrato | `test_paridade_contratos.py`, `test_comando.py` (casa o dict exato da instrução), `instrucoes.test.ts` (7 testes da regra de consumo) | pronta |

`executarInstrucoes` merece destaque: ele **já** decide o desfecho e **já** o
reduz a um booleano (`abrirApp` devolve `true`/`false`). Qualquer opção abaixo
é, do lado do cliente, uma chamada HTTP a mais nessa função — a informação já
está na mão, no lugar certo. O custo não está em descobrir o desfecho; está em
tudo o que o servidor teria que ganhar para recebê-lo.

Quatro propriedades do que existe condicionam todo o resto:

1. **Não existe id de correlação em lugar nenhum.** `ClientInstruction` não tem
   id, `AgentAction` não tem id, e `MensagemOut` não expõe o id da mensagem.
   Um relatório de resultado só consegue se referir a "a instrução do último
   comando da sessão X" — implícito e frágil — ou exige **campo novo no
   contrato**, com as duas pontas de `shared/` (seção 7).
2. **`actions` não são persistidas.** O banco não tem coluna nem tabela para
   ação de agente. Não existe linha onde pendurar um resultado: persistir
   significa tabela nova ou coluna nova, com migração.
3. **`messages` é append-only hoje.** Não há nenhum caminho que reescreva uma
   fala já gravada. A opção que corrige o buraco (b) muda isso.
4. **A regra de consumo não é representada por tipo nenhum** — vive nas
   docstrings dos dois `shared/`, com rede mecânica só indireta
   (`test_comando.py` para a invariante de segurança, `instrucoes.test.ts` para
   o consumo). Um endpoint de resultado passa a codificar **a mesma regra em um
   segundo lugar** (qual texto o cliente diz que falou), sem nada mecânico
   amarrando os dois. É superfície nova para a mesma mentira silenciosa que o
   mapa de impacto do `abrir_app` já classificou como a mudança mais perigosa
   deste contrato.

## 3. As opções

### A. Não fazer nada agora — manter anotado

Aceitar a divergência como ela está, e deixar o buraco (b) registrado com mais
precisão do que hoje (a anotação atual fala do `status`, não da **fala
gravada**).

- **Contrato:** intacto. Nenhum `shared/`, nenhuma paridade, nenhum cliente.
- **Custo:** zero.
- **O que perde:** fidelidade do histórico e do prompt no caminho de falha, e
  telemetria de app.
- **O que ganha:** a v1 fecha sem uma rota de escrita nova, sem migração e sem
  um campo obrigatório novo num contrato que dois clientes consomem — um deles
  congelado (seção 6).

### B. Só log — `POST /acao-resultado` sem persistência

O cliente reporta, o servidor escreve uma linha de `logger.info` e devolve
`204`. Nada é gravado no banco.

- **Correlação:** `session_id` + `type` bastam para uma linha de log. **Não
  exige id novo, não muda `ClientInstruction`.**
- **Custo:** o menor entre as opções que fazem algo. Uma rota, um contrato de
  entrada nos dois `shared/`, um balde de rate limit de escrita, testes. Sem
  migração, sem tocar no caminho de leitura, sem tocar em `messages`.
- **Resolve:** (c) — e responde a pergunta que ninguém respondeu ainda: *isso
  falha com que frequência?*
- **Não resolve:** (b). O histórico continua gravando a fala errada.
- **Ressalva:** log de servidor de instância única, sem agregação, é consultado
  a `grep`. Como fonte de telemetria é pouco melhor do que o `console.warn` que
  já existe no cliente — o ganho real é ficar no servidor, onde os dois
  clientes convergem.

### C. Resultado que **reescreve** a última fala do assistente

O relatório chega e o servidor substitui o conteúdo da última mensagem
`assistant` da sessão pelo texto que o cliente realmente falou.

- **Resolve (b) na veia**, e é a **única** opção que torna o prompt do comando
  seguinte verdadeiro.
- **Correlação:** "última mensagem do assistente da sessão". Sem id, é
  posicional — e a rota `/comando` é concorrente por natureza. Com um usuário e
  um aparelho por sessão o risco é teórico; com dois aparelhos na mesma sessão
  deixa de ser.
- **Custo:** médio. Método novo no repositório, rota, contrato de entrada nos
  dois `shared/`, balde de escrita, testes. Sem migração.
- **Preço de arquitetura:** `messages` deixa de ser append-only e passa a ser
  **mutável por relatório de cliente**. Um cliente com bug (ou um portador do
  token) reescreve o que o Shogun "disse". É decisão de arquitetura, não
  detalhe de implementação — seção 9.

### D. Resultado como fala nova (append em `messages`)

Em vez de reescrever, acrescenta uma mensagem `assistant` com o
`fallback_text`.

- **Custo:** o menor entre as que persistem — `registrar_assistente` já existe,
  nada de migração, nada de método novo.
- **Mas fica pior do que o problema.** O histórico passa a conter as **duas**
  falas, e o usuário ouviu **uma**. O prompt do comando seguinte recebe o
  Shogun se contradizendo em duas falas seguidas — exatamente o efeito que a
  regra de consumo ("nunca os dois") existe para evitar, reintroduzido pela
  porta do banco. **Desqualificada.**

### E. Tabela nova de instruções delegadas

`/comando` grava a instrução ao delegar; o relatório preenche o desfecho.

- **Resolve (a), (b) e (c)**, com idempotência de verdade (o id é a chave) e
  histórico de execução consultável.
- **Correlação:** id próprio, gerado no servidor — que precisa **viajar no
  contrato**, logo campo novo em `ClientInstruction`, nas duas pontas
  (seção 7).
- **Custo: o mais alto.** Migração, modelo, repositório, **escrita nova no
  caminho quente do `/comando`** (que hoje não grava nada sobre ações — passa a
  ter mais uma ida à threadpool por comando delegado), rota de resultado, balde
  de escrita, campo novo no contrato, testes nas duas pontas. E o mobile vira
  cidadão de segunda até implementar o relatório.
- **Observação:** é o desenho certo **se** o volume justificar. Para quatro apps
  curados e um usuário, é infraestrutura para um dado que ninguém consulta.

### F. Tabela satélite de `messages`, no molde de `messages_uso`

`messages_acao(message_id UNIQUE, …, resultado)` — o precedente já está no
schema e a forma é exatamente a mesma: existe só para algumas mensagens do
assistente, então coluna em `messages` seria nula na maioria das linhas.

- **Resolve (a), (b) e (c)**, mantendo `messages` append-only: a fala fica onde
  está e o resultado mora ao lado. `GET /sessoes/{id}/mensagens` poderia expor
  "o que foi falado de fato" sem reescrever nada.
- **Correlação:** `message_id`, que **não é exposto** por `MensagemOut` hoje. Ou
  se expõe o id (mudança nos dois `shared/` no contrato de leitura), ou o
  servidor resolve "a última do assistente desta sessão" (o posicional da
  opção C, com o mesmo porém).
- **Custo:** médio-alto. Migração + modelo + repositório + rota + contrato de
  entrada + balde + testes. Menos invasivo que E (não escreve no caminho quente
  do `/comando`), mais que C.

## 4. Comparação

| | Muda `ClientInstruction`? | Migração | Resolve (b) histórico | Resolve (c) telemetria | `messages` segue append-only | Custo |
|---|---|---|---|---|---|---|
| A. Não fazer | não | não | não | não | sim | **zero** |
| B. Só log | **não** | não | não | **sim** | sim | **baixo** |
| C. Reescreve a fala | não | não | **sim** | parcial | **não** | médio |
| D. Append de fala | não | não | piora | parcial | sim | baixo |
| E. Tabela de instruções | **sim** (id) | sim | sim | sim | sim | **alto** |
| F. Satélite de `messages` | não (mas expõe id) | sim | sim | sim | sim | médio-alto |

## 5. Sub-decisão: o que exatamente o cliente reporta?

Escolher uma opção não basta — falta dizer qual é o vocabulário. E aqui há uma
distinção que **não pode** ser achatada.

`executarInstrucoes` distingue hoje **três** desfechos, não dois:

1. `spawn` aceito pelo Tauri → falou `text`;
2. app **fora do mapa curado** (ou `type` desconhecido) → falou
   `fallback_text`, **sem nunca tocar no SO**;
3. `spawn` **recusado ou falhou** (permissão, executável ausente) → falou
   `fallback_text`.

**"Não suportado" não é a mesma coisa que "falha", e a diferença é a única parte
acionável do relatório.** O caso (2) é problema do **servidor**: o LLM nomeou um
app que aquele cliente não consegue abrir — é dado direto para o item "mapa de
apps configurável" do backlog, e eventualmente para o prompt. O caso (3) é
problema do **ambiente**: app não instalado, permissão negada; não há nada que o
servidor possa fazer. Colapsar os dois em "falhou" joga fora justamente o sinal
que valeria coletar.

**Proposta de vocabulário:** enum de três valores —
`ok` | `nao_suportado` | `falhou`.

Uma honestidade necessária sobre o `ok`: `abrirApp` usa `spawn`, não `execute`,
**de propósito** — abrir app é disparar-e-esquecer, e o `explorer.exe` devolve
código de saída diferente de zero mesmo quando abre. Logo **nenhum cliente
consegue reportar "o app abriu"**. O teto do que qualquer relatório pode afirmar
é *"consegui pedir ao SO"*. Quem aprovar este endpoint esperando saber que o
Spotify apareceu na tela vai receber algo mais fraco do que isso — e a
divergência da seção 1(a) encolhe, mas não desaparece.

**O erro cru entra?** **Não.** O precedente já está estabelecido no servidor, e
na direção oposta: `_DETALHE_FALHA_PROVEDOR` e `_DETALHE_LLM_INDISPONIVEL`
existem porque mensagem crua de exceção carrega caminho de arquivo, driver de
banco e URL de provedor. Na entrada vale o mesmo, agravado: um erro do Tauri
carrega caminho de executável, código de erro do Windows e, no caminho, o nome
de usuário. E se esse texto for **gravado** (opções C/E/F), ele volta a sair no
`GET /sessoes/{id}/mensagens` e pode entrar em `montar_prompt`. O erro cru fica
no `console.error` do cliente, onde já está.

Se um detalhe legível for desejado, que seja **string curta, curada pelo cliente
e com tamanho limitado** (ex.: `"fora do mapa curado"`) — e tratada como **texto
não confiável** onde for exibida ou, pior, injetada em prompt.

## 6. Impacto no mobile

O mobile é o **segundo consumidor do mesmo contrato**, está congelado até
pós-v1.0, e hoje re-exporta apenas `AgentAction` (`mobile/src/contracts.ts` →
`StatusScreen.tsx`): **nunca lê `instruction`**. Três consequências:

1. **Campo novo em `ClientInstruction` não quebra o mobile.** Ele só lê o
   contrato, nunca constrói uma instrução; campo extra é ignorado, o `tsc`
   passa. Baixo risco — e também nenhum benefício: campo inerte por meses.
2. **No mobile, `nao_suportado` é a regra, não a exceção.** `Linking.openURL`
   exige schemes declarados de antemão (`LSApplicationQueriesSchemes` no iOS,
   `<queries>` no Android 11+), então o mobile só abre uma **lista curada**, e
   ela é mais restrita que a do desktop. Isto inverte o valor da telemetria: o
   consumidor cujos dados seriam interessantes é exatamente o que **não pode
   produzir dado nenhum agora**. Qualquer métrica coletada hoje é desktop-only,
   e vai parecer outra coisa depois do descongelamento.
3. **Um endpoint implementado agora nasce com um cliente que não o chama.** O
   servidor passaria a ter um caminho de escrita que só o desktop exercita, e a
   ausência de relatório do mobile seria indistinguível de "não executou".

Achado de documentação, para o coordenador — **não corrigido aqui, porque este
documento não altera outros**: a seção 6 de `docs/plano-integracao-mobile.md`
está **desatualizada**. Ela ainda descreve `abrir_app` como placeholder
resolvido no servidor, com `status: "error"`, e afirma que "não há nada para o
cliente executar hoje" e que o contrato "ainda não existe". Foi escrita antes de
a delegação por `ClientInstruction` entrar. Quem descongelar o mobile vai ler
uma descrição errada do contrato que precisa implementar.

## 7. Se mudar `ClientInstruction`, muda nas duas pontas

Só as opções E (id de instrução) e F (id de mensagem no contrato de leitura)
exigem mexer no contrato. As regras, para quem for implementar:

- `shared/python` e `shared/ts` são **um contrato só, escrito duas vezes** —
  mesma branch, e de preferência mesmo commit. `test_paridade_contratos.py` lê
  `shared/ts/index.ts` **como texto** e compara contratos, campos,
  opcionalidade e tipos contra os `BaseModel`. Mexer num lado só **quebra o
  CI**, e é para isso que o teste existe.
- `test_acao_abrir_app_delega_ao_cliente` (`server/tests/test_comando.py`) casa
  o **dict exato** da instrução: campo novo faz ele falhar. Isso é o tripwire
  funcionando, não um estorvo.
- O desktop **compila mesmo assim** (só lê a instrução), então o erro possível
  aqui é silencioso: contrato novo, cliente sem implementar. A rede é
  `instrucoes.test.ts`.
- Se o vocabulário da seção 5 virar um `Literal`/union no contrato de entrada,
  ele também precisa das duas pontas — e valor novo (um `type` futuro, um
  desfecho novo) segue a mesma convenção de degradação elegante que o
  `ClientInstruction` já tem.

## 8. Recomendação

**Não implementar `POST /acao-resultado` agora. Manter anotado — e sair desta
rodada com a anotação mais honesta do que ela é hoje.**

O raciocínio, sem rodeio:

- **Para um usuário só, o próprio usuário é o canal de retorno.** O Marcus está
  na frente do aparelho: ele **vê** se o Spotify abriu, e o cliente já lhe diz
  em voz alta quando não abriu. O servidor saber o desfecho não muda uma única
  resposta que ele vai dar.
- **O buraco (a) é convenção documentada, não bug** — custo prático zero.
- **O buraco (c) vale menos do que parece.** Telemetria sobre um mapa de quatro
  apps curados, coletada só no desktop, enquanto o cliente onde
  `nao_suportado` seria o caso comum está congelado. O dado já existe no
  `console.warn`.
- **O buraco (b) é real, e é o único que eu levaria a sério.** Mas o remédio
  (opção C) torna `messages` **mutável por relatório de cliente**, e as opções
  que o resolvem preservando o append-only (E, F) custam migração + campo novo
  em contrato compartilhado. Nenhum desses preços se paga por um histórico que,
  hoje, é reexibido por um usuário que lembra o que aconteceu.
- E o teto do que o endpoint pode afirmar é *"consegui pedir ao SO"* (seção 5),
  não *"o app abriu"*. O buraco (a) encolhe; não fecha.

**O que fazer em vez disso (custo baixo, por outro agente, não nesta branch):**

1. **Afinar a anotação nos dois `shared/`.** A docstring de
   `AgentAction.instruction` hoje registra que `status: ok` = delegação feita.
   Ela **não** registra que o histórico grava o `text` mesmo quando o cliente
   falou o `fallback_text` — que é a consequência com efeito observável,
   inclusive no prompt do comando seguinte. Uma frase nas duas pontas. *(Fora do
   escopo desta rodada: mexer em `shared/` exige as duas pontas na mesma branch,
   e o enunciado desta tarefa proíbe alterar `shared/`.)*
2. **Corrigir a seção 6 de `docs/plano-integracao-mobile.md`** (seção 6 acima).

**Se e quando entrar, a ordem é B → F, nunca E primeiro.** B (só log) custa
pouco, não toca contrato nem banco, e responde a pergunta que ainda não tem
resposta: *com que frequência isso falha, e com quais nomes de app?* Só se o log
mostrar volume real é que F se paga — e é aí que um id no contrato passa a ser
justificado por um consumidor concreto, em vez de por simetria de desenho.

**Gatilhos concretos para reabrir a decisão** (qualquer um basta):

- o **mobile descongela** e passa a executar instruções — `nao_suportado` vira o
  caso comum e a telemetria fica útil;
- o **mapa de apps configurável** entra: quem configura precisa saber quais
  nomes o LLM manda e falham;
- passa a existir **mais de um aparelho ou mais de um usuário** — o usuário
  deixa de ser o canal de retorno, e o posicional das opções C/F deixa de ser
  seguro;
- o **histórico de sessão vira coisa que se relê**, ou aparece caso concreto de
  o prompt confundir o LLM por causa da fala errada gravada.

## 9. O que **não** está decidido aqui

Tudo abaixo é de arquitetura ou de coordenação, e precisa de aval antes de
qualquer implementação:

1. **A decisão principal: implementar agora ou manter anotado.** A recomendação
   é **manter anotado** (seção 8). "Não vale, deixa anotado" é a conclusão
   honesta — mas a chamada é do Marcus.
2. **Se implementar, qual opção.** B (só log), C (reescreve a fala), E (tabela
   de instruções) ou F (satélite de `messages`). D está desqualificada
   tecnicamente (seção 3). A ordem recomendada é B → F.
3. **`messages` pode deixar de ser append-only?** A opção C reescreve uma fala
   já gravada, por relatório de cliente. Muda a semântica da tabela e a
   confiança do histórico. É a pergunta de arquitetura mais pesada deste
   documento.
4. **O vocabulário do relatório:** três valores
   (`ok`/`nao_suportado`/`falhou`) ou booleano. A recomendação é três — e a
   escolha vira contrato compartilhado que desktop **e** mobile vão consumir.
5. **Detalhe livre no relatório, sim ou não.** Se sim, é string curta e curada
   pelo cliente, com limite de tamanho, tratada como texto não confiável onde
   for exibida ou injetada em prompt. Erro cru **nunca** entra (seção 5).
6. **Campo novo em `ClientInstruction`** (`instruction_id`) — obrigatório num
   contrato que dois clientes consomem, inerte no mobile por meses. Só se
   justifica com persistência (E). Precisa das duas pontas de `shared/` na mesma
   branch.
7. **Confiança no relatório.** Ele é **auto-declarado** sob o mesmo token Bearer
   único e compartilhado — a mesma ressalva do `agente_id` em
   `docs/produtor-pendencias.md`. Um relatório vale exatamente o que vale o
   portador do token. Em servidor de usuário único atrás de Tailscale é
   aceitável; é aceitação consciente, não esquecimento.
8. **Balde de rate limit de escrita.** Qualquer opção que não seja A cria a
   primeira rota de escrita vinda de cliente. Os baldes existentes são `comando`
   e `leitura`; um relatório é barato, mas dispara junto de cada comando
   delegado. Mesma sub-decisão pendente em `docs/produtor-pendencias.md` — se as
   duas rotas entrarem, o balde deveria ser **um só**, decidido de uma vez.
9. **Divisão de trabalho.** O contrato é do **agente-contratos**; a rota é do
   **agente-backend** (`server/app/api/`); o relatório sai do
   **agente-desktop** (`instrucoes.ts`), e um dia do mobile. Três áreas para uma
   feature — se ela entrar, a divisão é da coordenação.
