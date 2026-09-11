# Revisão de consumidor: `ClientInstruction` / `abrir_app` — assento do mobile

> **Documento só. O mobile continua congelado.** Nenhuma linha de código,
> nenhuma dependência, nenhuma mudança de scaffold saiu desta revisão. O
> descongelamento é decisão do Marcus e nada aqui o antecipa — o que segue é o
> papel de *revisor consumidor*, o mesmo que já se pagou uma vez quando o
> mobile revisou o PR #24 antes do merge.

Escopo: o contrato `ClientInstruction` / `AgentAction.instruction` como ele
está em `dev` (`de273b9`), lido do ponto de vista de quem terá que honrá-lo em
Android e iOS. Alvo da crítica é o **contrato**, não o desktop — o desktop já
o implementa e serve aqui de referência de como o outro consumidor resolveu.

Lidos para esta revisão: `shared/python/__init__.py`, `shared/ts/index.ts`,
`server/app/api/comando.py`, `server/tests/test_comando.py`,
`desktop/src/lib/instrucoes.ts`, `desktop/src/lib/instrucoes.test.ts`,
`desktop/src-tauri/capabilities/default.json`,
`docs/plano-integracao-mobile.md` e o scaffold em `mobile/src/`.

---

## 1. Sumário executivo

O contrato está **bom**, e a decisão central dele — o servidor manda só o NOME
do app, o mapeamento nome → alvo é sempre do cliente — é exatamente a que o
mobile precisava. Ela sobreviveu ao contato com dois consumidores muito
diferentes sem precisar de campo novo. Isso é raro e vale registrar.

Existem **quatro achados** que merecem decisão antes de o mobile encostar no
contrato, dois deles de contrato mesmo (não de implementação):

| # | Achado | Gravidade | Custo de arrumar agora |
|---|--------|-----------|------------------------|
| A1 | A regra de consumo manda **executar antes de falar**. No celular, executar *bota o app de voz em segundo plano* — a fala do `text` acontece num app que acabou de perder o foreground. | **Contrato.** Bloqueia a implementação do mobile como escrita hoje. | Uma frase em duas docstrings. Zero mudança no desktop. |
| A2 | O contrato não diz **quantas** instruções uma resposta pode carregar. O desktop executa só a primeira e ignora o resto (`.find(...)`); nada no contrato diz que isso é certo. | **Contrato.** Risco de os dois clientes divergirem em silêncio. | Uma frase em duas docstrings. |
| A3 | A justificativa técnica sobre mobile que está *dentro* das docstrings (`Linking.openURL` exigiria schemes declarados) aponta para a API errada — a restrição recai sobre `canOpenURL`. | Documental, mas mora no contrato e é lida como verdade. | Uma frase em duas docstrings + na seção 6 do plano. |
| A4 | O servidor grava no histórico da sessão o `text` **otimista** ("Pedi para este aparelho abrir o X"), mesmo quando o cliente caiu no `fallback_text`. Com `GET /sessoes/{id}/mensagens` já existindo, trocar o histórico local pelo do servidor **apaga o fallback** e passa a mostrar um sucesso que não houve. | Comportamento. Atinge desktop e mobile. | Decisão de produto; nenhuma saída é grátis. |

Além disso: a seção 6 inteira de `docs/plano-integracao-mobile.md` está
**factualmente morta** (detalhe na seção 5 desta revisão), e um bloqueio de
processo — não de contrato — espera o mobile na porta: implementar `open_app`
tira o app do Expo Go, e o mobile não tem suíte de testes nem check de CI
(seção 6).

---

## 2. O que o mobile recebe hoje, exatamente

Depois do PR #41, o fio que chega ao cliente é estreito e previsível:

```jsonc
{
  "session_id": "…",
  "text": "Pedi para este aparelho abrir o Spotify, Marcus.",
  "actions": [{
    "agent": "sistema",
    "status": "ok",
    "detail": "execução delegada ao cliente (app=Spotify)",
    "instruction": {
      "type": "open_app",
      "app": "Spotify",
      "fallback_text": "Não consegui abrir o Spotify neste aparelho, Marcus."
    }
  }]
}
```

Garantias que o mobile pode assumir, e de onde elas vêm:

- **`app` é um nome simples.** `_APP_PROIBIDO = (":", "/", "\\")` em
  `server/app/api/comando.py` recusa scheme, caminho POSIX, caminho Windows,
  UNC e URL inteira *antes* de virar instrução —
  `test_abrir_app_recusa_nome_que_nao_seja_nome` cobre os cinco casos. Isso é
  **comportamento**, não promessa de docstring: virou guarda no PR #41.
- **Quando o nome é recusado, não vem instrução nenhuma.** A action volta com
  `status: "error"` e `instruction: null`, e o nome hostil não é ecoado nem na
  fala nem no `detail`. Um cliente que só olhasse `instruction` não recebe
  alvo executável nem por acidente.
- **`fallback_text` vem pronto.** O cliente nunca redige resposta.
- **`status: "ok"` significa delegação feita, não app aberto.** Está na
  docstring e é divergência aceita na v1.

Nada disso depende do campo `client` do `CommandRequest`: o servidor emite a
mesma instrução para desktop e mobile. **Isso está certo** — ver seção 7.4.

---

## 3. Achado A1 — a regra de consumo é desktop-shaped

Este é o achado que importa.

A regra, literal nos dois `shared/`:

> o cliente tenta executar ANTES de falar. Sucesso: fala `text`. Falha ou app
> não suportado: fala `fallback_text` EM VEZ de `text` — nunca os dois.

No desktop isso é natural: `Command.create(...).spawn()` lança `explorer.exe`,
a janela do Shogun pode perder o foco mas o processo continua vivo e o TTS
segue tocando. Executar antes de falar não custa nada.

No celular, **executar é sair**. `Linking.openURL` traz o app alvo para o
foreground e manda o Shogun para o background. A sequência do contrato vira,
na prática:

1. abre o Spotify → Shogun vai para segundo plano;
2. …o Shogun agora tenta falar `text`.

No iOS o passo 2 não acontece de forma confiável: a síntese de voz é
interrompida quando o app deixa o foreground, a menos que a sessão de áudio
esteja configurada para rodar em background (`UIBackgroundModes: audio`) — uma
declaração pesada, que atrai escrutínio de review na App Store e que o Shogun
não tem hoje. No Android o TTS do sistema costuma sobreviver, mas depender
disso significa que **o mesmo contrato produz comportamento diferente nas duas
plataformas do mesmo cliente**.

O resultado, se o mobile implementar a regra ao pé da letra, é o pior dos
mundos: no caminho de **sucesso** o usuário não ouve nada (o `text` morre no
background) e no caminho de **falha** ele ouve o `fallback_text` normalmente.
A voz só funciona quando dá errado.

### 3.1 Por que isso é de contrato, e não "o mobile que se vire"

Porque a saída óbvia — falar primeiro, abrir depois — é **proibida pelo texto
atual**. O cliente não tem como escolher *qual* dos dois textos falar sem já
ter tentado executar. A regra amarra duas coisas que não precisam estar
amarradas:

- **decidir** qual texto é o certo; e
- **executar** a abertura.

O desktop pode fazer as duas no mesmo passo porque, para ele, "consigo abrir" e
"abri" são indistinguíveis. O mobile precisa separá-las.

### 3.2 A separação existe e é barata

No mobile, decidir antes de executar é possível e é justamente para isso que
serve `Linking.canOpenURL` (iOS) / a checagem de resolução de intent (Android).
O fluxo vira:

1. resolve `app` no mapa curado local → se não achar, fala `fallback_text` e
   acabou (nem tenta abrir);
2. se achou, pergunta ao SO se dá para abrir aquele alvo;
3. **fala `text`** (ou `fallback_text`, conforme o passo 2);
4. **depois** chama `openURL`.

Isto honra o espírito do contrato — exatamente um dos dois textos, escolhido
pela viabilidade real — e resolve a ordenação. E tem um efeito colateral bom:
é o passo 2 que torna a declaração prévia de schemes
(`LSApplicationQueriesSchemes` / `<queries>`) **genuinamente obrigatória** no
mobile, que é o que as docstrings já queriam dizer (ver A3).

O custo para o desktop é **zero**: para ele, decidir e executar continuam sendo
o mesmo passo, e `executarInstrucoes` não muda uma linha.

### 3.3 Recomendação

**R1 (recomendado, fazer antes do descongelamento).** Reescrever a regra nos
dois `shared/` de "tenta executar ANTES de falar" para algo como:

> O cliente **decide** qual dos dois textos vale **antes de falar**: se ele
> consegue executar a instrução, fala `text`; se não consegue — alvo fora da
> lista curada, `type` desconhecido, SO recusa —, fala `fallback_text` EM VEZ
> de `text`, nunca os dois. **Quando** a execução acontece em relação à fala é
> do cliente: no desktop decidir e executar são o mesmo passo; no mobile abrir
> outro app manda o Shogun para segundo plano, então a fala vem antes.

Nota de risco honesta: com a fala antes da execução, abre-se uma janela em que
o Shogun diz "pedi para abrir o Spotify" e o `openURL` falha logo depois. É uma
janela estreita (o `canOpenURL` já passou) e o preço dela é menor que o do
caminho de sucesso ser mudo. Vale registrar a escolha, não escondê-la.

---

## 4. Deep link e intent: detalhe ou problema de contrato?

Resposta curta: **quase tudo é detalhe de implementação, e isso é mérito do
contrato.** Duas coisas não são.

### 4.1 O que é detalhe (e o contrato lida bem)

- **Não existe no mobile o equivalente ao `capabilities/default.json`.** No
  desktop, o escopo do `tauri-plugin-shell` fixa executável e args por comando
  nomeado, então nem o código do cliente consegue rodar outra coisa. No mobile
  a trava equivalente é outra: o mapa curado é uma tabela fechada em código e
  os schemes precisam estar declarados no `Info.plist`/`AndroidManifest`.
  Mecanismo diferente, **mesma propriedade**: string vinda do servidor nunca
  vira alvo. O contrato não precisa saber qual dos dois é.
- **Depois do PR #26 os dois clientes são igualmente curados.** O plano ainda
  diz que o desktop "pode lançar processos arbitrários" — deixou de ser
  verdade. Os dois convergiram para lista fechada, o que enfraquece a ideia de
  que o mobile é o caso especial restrito.
- **Mapa por plataforma.** Alguns apps têm scheme no iOS e nenhum no Android
  (onde abrir por *package* exige `getLaunchIntentForPackage`, que o `Linking`
  do RN não expõe — precisaria de `expo-intent-launcher` ou módulo nativo).
  Consequência: o mesmo `app` pode ser suportado no iPhone e não no Android,
  **dentro do mesmo `client: "mobile"`**. O contrato já trata isso de graça,
  porque a viabilidade é decidida por aparelho e o `fallback_text` é por
  resposta. Nenhuma mudança necessária.
- **Lista curada pequena.** O iOS limita `LSApplicationQueriesSchemes` a 50
  entradas. Longe de ser um problema para um mapa de 4–10 apps.

### 4.2 O que **não** é detalhe

1. **A ordenação fala × execução** — achado A1, seção 3. É a única coisa em que
   a natureza do "abrir app" no celular contradiz o texto do contrato.
2. **A lista curada do mobile é de *build*, não de código.** No desktop,
   `capabilities/default.json` também é build-time, mas "build" ali é
   recompilar e distribuir um binário que o Marcus controla. No mobile, mudar
   os schemes declarados exige novo build **e nova submissão à loja**. O
   comentário do desktop — "configurável fica para depois" — não tem
   equivalente possível no mobile: no celular, *configurável por schemes
   arbitrários nunca vai existir*. Isso não muda o contrato (que já põe o mapa
   no cliente), mas muda a expectativa de produto: "adicionar o app X ao
   Shogun" é uma release de loja, não uma configuração.

---

## 5. O que ficou desatualizado em `docs/plano-integracao-mobile.md`

Por seção, do mais grave para o menos.

### Seção 6 — `AgentAction` e `abrir_app`: **morta, reescrever inteira**

Todas as afirmações factuais dela caíram:

| Texto do plano | Estado real |
|---|---|
| "`CommandResponse.actions` é **informativo**, não executável" | Falso desde o PR #24. `AgentAction.instruction` é executável por definição. |
| "`AgentAction` carrega `agent`, `status` e `detail` — nada que instrua o cliente" | Falso: carrega `instruction`. |
| "`abrir_app` hoje é resolvido inteiramente no servidor como placeholder… a resposta falada já diz 'essa ação está em construção' e a action vem com `status: "error"`" | Falso. `_abrir_app` devolve `status: "ok"` com instrução; `error` ficou só para os casos de `app` ausente ou recusado pela guarda do #41. |
| "**Não há nada para o cliente executar hoje.**" | Falso. O desktop executa desde o PR #26. |
| "esse contrato ainda não existe e a decisão é do servidor/`shared/`… precisará de um campo **estruturado** novo (ex.: uma instrução com o nome do app)" | Cumprido: é exatamente o `ClientInstruction`. O parágrafo deve virar registro histórico ("foi assim que se pediu, foi assim que veio"), não pendência. |
| "é diferente do desktop, que pode lançar processos arbitrários" | Falso desde o #26: o desktop tem mapa curado travado pelo escopo do `tauri-plugin-shell`. |
| "`Linking.openURL` exige schemes declarados" | Impreciso — ver A3 / seção 7.3. |
| "`abrir_app` não entra em nenhum passo da ordem do item 7" | A conclusão ainda é defensável como *sequenciamento*, mas a justificativa ("o contrato não existe") morreu. Precisa de razão nova ou de um passo novo no item 7. |

O único trecho da seção 6 que envelheceu **bem** é o penúltimo parágrafo, o
"registro antecipado da restrição do lado mobile": ele pediu que o contrato não
obrigasse o cliente a abrir alvo arbitrário, e o contrato veio assim. Vale
manter, marcado como atendido.

### Seção 4 — offline e falhas: um item caducou

> "o servidor guarda o histórico, mas não há endpoint de leitura hoje — quando
> houver, o local vira só cache"

O endpoint **já existe**: `GET /sessoes` e `GET /sessoes/{id}/mensagens`
(`server/app/api/sessoes.py`, tipados em `shared/ts` como `SessoesResponse` /
`MensagensResponse`). E o plano de "o local vira só cache" agora **colide com o
`abrir_app`** — ver achado A4, seção 7.5. O resto da seção 4 (sem fila offline,
reenvio manual, timeouts, nunca reenviar `POST /comando` automaticamente)
continua válido e não foi tocado por #26/#41.

### Seção 5 — o que espelhar do desktop: incompleta

- "**Exibição de `actions`** como metadado" precisa da ressalva de que uma
  action pode carregar instrução executável — exibir não basta mais.
- A lista manda espelhar `desktop/src/lib/api.ts` e `config.ts`. Falta
  `desktop/src/lib/instrucoes.ts` e `instrucoes.test.ts`, que hoje são a
  referência de implementação **e** a única rede mecânica da regra de consumo.
- "**STT/TTS** … não altera nada da integração acima" (também no item 7.5)
  deixou de valer: o TTS é exatamente onde o achado A1 dói. Voz e `abrir_app`
  não são independentes no mobile.

### Seção 7 — ordem de implementação: falta um passo

Os passos 1–4 continuam corretos e continuam não dependendo de `abrir_app`. Mas
a ordem precisa de um item explícito para execução de instruções (mapa curado +
declaração de schemes + regra de consumo), hoje inexistente porque o plano
assumia que não havia o que executar.

### Seção 1 — ponto de partida: nota menor

`mobile/src/contracts.ts` é descrito como "cópia fiel de `shared/ts`". Ele é um
re-export e reexporta só `AgentAction`, `CommandRequest` e `CommandResponse` —
**`ClientInstruction` não está na lista**. É uma linha de trabalho normal, mas
enquanto ela não existir o app não enxerga o tipo do campo que vai consumir.

### Seções 2 e 3 — intactas

`session_id` no AsyncStorage e token no SecureStore não foram tocados por
#26/#41. Seguem válidos como estão.

---

## 6. Bloqueio de verdade × trabalho normal

Quando o descongelamento vier, para o item `AgentAction`/`abrir_app`:

### Bloqueio de verdade (precisa de decisão, não de código)

1. **A ordenação fala × execução (A1).** Enquanto a regra disser "executar
   antes de falar", a implementação correta do mobile é a que produz o caminho
   de sucesso mudo. Não dá para "resolver na implementação" sem contrariar o
   contrato por escrito. → decisão do Marcus sobre R1.
2. **Sair do Expo Go.** Declarar `LSApplicationQueriesSchemes` e `<queries>`
   exige config plugin e **development build** (EAS). O Expo Go não permite
   declarar schemes arbitrários. Ou seja: o primeiro PR de `open_app` no mobile
   muda o fluxo de desenvolvimento do projeto inteiro, e é o momento em que o
   mobile passa a precisar de pipeline de build. Não é decisão de contrato, mas
   é grande demais para um agente decidir sozinho.
3. **Suíte e check de CI do mobile.** `mobile/package.json` não tem script de
   teste. A regra de consumo é a parte do contrato que **nenhum tipo
   representa** — no desktop ela só não mente porque `instrucoes.test.ts`
   existe. Replicar essa rede no mobile significa runner novo (jest/vitest),
   dependências novas e um **quarto check** no CI — e a proteção de `dev` é
   estrita e lista os checks pelo nome, então habilitá-lo é mexer em
   configuração do repositório. Decisão do Marcus.
4. **Qual é a lista curada do mobile** — e a aceitação de que mudá-la é release
   de loja (seção 4.2). Decisão de produto.

### Trabalho normal (só implementar, quando liberar)

- O mapa curado, os sinônimos e `normalizar()`: praticamente transplantáveis de
  `desktop/src/lib/instrucoes.ts` — a normalização (minúsculas, sem acentos,
  espaços colapsados) é idêntica nas duas plataformas.
- A função de seleção `text` × `fallback_text`, espelhando `executarInstrucoes`.
- Reexportar `ClientInstruction` em `mobile/src/contracts.ts`.
- Renderizar `actions` como metadado discreto, bengara só em `status: "error"`.
- Tratar `type` desconhecido caindo no `fallback_text` (a convenção do contrato
  garante que ele sempre existe).

Ponto a favor do contrato: essa lista é curta, e é curta porque o contrato não
obrigou o mobile a nada específico de plataforma.

---

## 7. O que deveria mudar no contrato antes de o mobile encostar

Ordenado por relação custo/benefício. Nenhuma destas mudanças foi feita nesta
branch — `shared/` não foi tocado, como pedido.

### 7.1 R1 — reescrever a regra de consumo como "decidir antes de falar"

**Recomendado.** Detalhado na seção 3.3. Duas docstrings, zero mudança de
comportamento no desktop, desbloqueia o mobile. É o item mais barato e o mais
importante desta revisão.

### 7.2 R2 — dizer quantas instruções uma resposta pode carregar (A2)

**Recomendado.** O contrato é silencioso. O desktop resolveu com
`resposta.actions.find((a) => a.instruction != null)?.instruction` — pega a
primeira e ignora as demais, e há teste para isso ("pega a primeira action que
carrega instrução, ignorando as informativas"). Mas esse teste testa a *escolha
do desktop*, não uma regra do contrato: um implementador do mobile lendo só
`shared/` pode razoavelmente iterar sobre todas e executar várias.

Hoje o servidor emite no máximo uma action por comando, então a divergência
seria invisível — até o dia em que não fosse. Sugestão: fixar no contrato **"no
máximo uma instrução por resposta; o cliente executa a primeira e ignora o
resto"**. Uma frase, e os dois clientes passam a estar certos pelo mesmo
motivo.

### 7.3 R3 — corrigir (ou despersonalizar) a afirmação sobre o mobile (A3)

**Recomendado.** As duas docstrings de `ClientInstruction` afirmam que
`Linking.openURL` exige schemes declarados em `LSApplicationQueriesSchemes` /
`<queries>`. A restrição de declaração prévia, nas duas plataformas, recai
sobre a **consulta de viabilidade** (`canOpenURL`, que no Android resolve via
`resolveActivity` e portanto passa pelo filtro de visibilidade de pacotes), não
sobre a abertura em si — um `openURL`/`startActivity` implícito não é filtrado,
ele só falha se ninguém souber tratar a URL.

A conclusão do contrato ("no mobile só uma lista curada é viável") continua
**certa** — e fica mais forte com R1, porque aí o `canOpenURL` passa a ser o
passo que decide o texto, tornando a declaração prévia obrigatória de fato. Só
a API citada está trocada.

Duas formas de arrumar, e prefiro a segunda:

- corrigir para `canOpenURL`; ou
- **tirar o nome da API do contrato** e dizer a propriedade, que é
  platform-neutral: *"clientes móveis só conseguem abrir alvos declarados no
  build; a lista é necessariamente curada e fechada"*. Assim o contrato para de
  carregar um fato de plataforma que envelhece, em dois arquivos que precisam
  andar juntos.

> Nota de honestidade do revisor: a distinção `openURL` × `canOpenURL` acima é
> a leitura da documentação das duas plataformas, **não foi verificada em
> aparelho** (o mobile está congelado e esta revisão não roda código). Se ela
> virar base para redigir o contrato, confirmar em device no primeiro PR do
> mobile. A recomendação de despersonalizar o texto tem a vantagem de não
> depender dessa verificação.

### 7.4 R4 — o que **não** deve mudar

Registrado aqui porque são propostas previsíveis, e é mais barato responder
agora do que re-litigar depois.

- **Não transformar `app` em `Literal`/enum no `shared/`.** Seria a reação
  natural de quem quer segurança de tipo, e seria um erro: colocaria a lista de
  apps **no servidor**, obrigaria servidor e os dois clientes a subirem juntos
  a cada app novo, e quebraria a propriedade que faz este contrato funcionar
  para dois consumidores tão diferentes — cada cliente suporta o que consegue,
  e o `fallback_text` cobre o resto. O mundo aberto aqui é deliberado.
- **Não fazer o servidor variar a instrução por `client`.** O `CommandRequest`
  tem `client: "desktop" | "mobile"`, e é tentador usá-lo para o servidor
  "saber" o que cada cliente abre. Isso reintroduziria no servidor exatamente o
  acoplamento que o contrato tirou — e nem funcionaria, já que a viabilidade no
  mobile varia por **plataforma e por aparelho** (app instalado ou não), coisa
  que o servidor não tem como saber. O `fallback_text` já é client-agnostic
  ("neste aparelho") e está correto como está.
- **Não permitir que o cliente concatene ou reescreva os textos.** No mobile
  vai aparecer a vontade de distinguir "app não instalado" de "app não
  suportado pelo Shogun" — são causas diferentes com o mesmo `fallback_text`. A
  regra "exatamente um dos dois, nunca os dois" deve continuar valendo **na
  fala**; se a distinção importar, ela é detalhe de UI da bolha do chat, não de
  contrato.
- **Não fazer o Android cair no `market://` quando o app não está instalado.**
  Abrir a Play Store conta como `openURL` bem-sucedido, e o Shogun falaria
  "pedi para este aparelho abrir o Spotify" enquanto a loja aparece na tela —
  o `text` viraria mentira. Se algum dia isso for desejável, é `type` novo de
  instrução, não um atalho dentro do `open_app`.

### 7.5 R5 — decidir o que fazer com o histórico otimista (A4)

**Precisa de decisão; não bloqueia o mobile, mas está ficando mais caro.**

`_fechar_conversa` grava na sessão a `resposta` produzida por `_abrir_app` —
isto é, sempre o texto otimista *"Pedi para este aparelho abrir o X, Marcus."* —
independentemente de o cliente ter conseguido abrir. Isso é coerente com
"`status: "ok"` = delegação feita", já documentado como divergência aceita na
v1.

O que ninguém registrou é a consequência agora que `GET /sessoes/{id}/mensagens`
existe: **ao reabrir a conversa, o fallback desaparece**. O usuário ouviu "não
consegui abrir o Spotify", e o histórico do servidor conta que o Shogun pediu
para abrir. Isso já é verdade no desktop (que tem tela de conversas); no mobile
fica pior, porque o plano (seção 4) prevê justamente trocar o histórico local
pelo do servidor assim que houver endpoint — e o endpoint chegou.

Três saídas, nenhuma grátis:

- **aceitar e documentar** — barato, e talvez o certo para a v1, desde que
  fique escrito no lugar certo (hoje não está em lugar nenhum);
- **o cliente reportar o resultado** (o `POST /acao-resultado` que a docstring
  já menciona como extensão futura) — resolve de verdade, custa rota nova,
  contrato novo e uma escrita a mais por comando;
- **o servidor gravar texto neutro** ("Pedi para abrir o Spotify") e deixar o
  otimismo só na fala do momento — mais barato que a rota nova, mas faz o
  histórico divergir do que foi falado, que é o problema de origem.

Recomendo **aceitar e documentar** na v1, e registrar a rota como extensão —
mas a decisão é do Marcus, e o lugar de registrar é o contrato, não este
documento.

---

## 8. Uma regra que o mobile precisa se impor (e que o contrato deveria dizer)

A guarda do PR #41 impede que `:` `/` `\` cheguem ao cliente. Isso é o que
torna seguro o mapeamento nome → alvo — **desde que o cliente faça lookup em
tabela fechada e nunca construa URI a partir de `app`**.

O desktop honra isso por construção: `APPS_CURADOS[chave]` é lookup puro, e
mesmo que não fosse, o escopo do `tauri-plugin-shell` recusaria o spawn. No
mobile não existe essa segunda trava: montar a URL concatenando o `app` compila,
roda e parece razoável para quem está implementando. A guarda do servidor
limitaria o estrago (sem `:` e sem `/`, não dá para montar payload), mas a
segurança passaria a depender de um *filtro de caractere* em vez de um mundo
fechado — e o filtro é por caractere ASCII, então um homógrafo (dois-pontos de
largura total, por exemplo) atravessa. Em tabela fechada isso é irrelevante: o
nome simplesmente não está no mapa e vira `fallback_text`.

Hoje o invariante do contrato só constrange o **servidor** ("nunca envia URI,
scheme ou comando executável"). Sugestão de complemento, na mesma docstring:

> …e o cliente **nunca constrói** URI, scheme ou comando a partir de `app`: o
> alvo sai sempre de uma tabela fechada do próprio cliente. É essa combinação —
> servidor manda nome, cliente resolve por lookup — que garante que o LLM não
> aponta para alvo arbitrário.

Custo: uma frase em dois arquivos. Benefício: a garantia deixa de depender de o
implementador do próximo cliente ter lido esta revisão.

---

## 9. O que precisa de decisão do Marcus

1. **R1** — reescrever a regra de consumo para "decidir antes de falar"
   (seção 3.3). Sem isso, o mobile não tem implementação correta *e* fiel ao
   contrato. **É o único item que bloqueia.**
2. **R2** — fixar no contrato quantas instruções uma resposta carrega
   (seção 7.2).
3. **R3** — corrigir ou despersonalizar a afirmação sobre `Linking.openURL` nas
   duas docstrings (seção 7.3).
4. **R5 / A4** — o que fazer com o histórico otimista agora que
   `GET /sessoes/{id}/mensagens` existe (seção 7.5). Atinge o desktop também.
5. Complemento do invariante: "o cliente nunca constrói URI a partir de `app`"
   (seção 8).
6. Fora do contrato, mas na porta do mobile: **development build/EAS** (sai do
   Expo Go) e **suíte + quarto check de CI** para o mobile (seção 6).
7. Reescrita da seção 6 de `docs/plano-integracao-mobile.md`, que está
   factualmente morta (seção 5). Não foi feita aqui: o plano é documento
   aprovado em PR (#17) e reescrevê-lo é decisão, não manutenção.

Itens 1, 2, 3 e 5 são, somados, **algumas frases em dois arquivos**. O momento
de gastá-las é agora, com um consumidor só implementado — depois de o mobile
encostar, cada uma vira mudança coordenada em três lugares.
