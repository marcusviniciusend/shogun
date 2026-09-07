# Plano de integração do mobile com `POST /comando`

> **Status: plano para aprovação — nenhuma linha de código.** O mobile segue
> congelado para implementação (a paleta washi do PR #16 foi exceção
> autorizada). Este documento descreve como o app React Native fará a
> integração com o servidor quando o congelamento for levantado, espelhando o
> que o desktop está implementando agora na versão texto-primeiro.

## 1. Ponto de partida

O `mobile/src/` já contém um esqueleto escrito antes do congelamento —
`api.ts`, `storage.ts`, `contracts.ts` e as telas Chat/Status/Config. O plano
**parte desse esqueleto** em vez de propor outro desenho: a estrutura está
correta e alinhada ao desktop. O que este plano faz é (a) validar as decisões
já esboçadas, (b) apontar o que precisa mudar antes de ir adiante (o token no
AsyncStorage, item 3) e (c) definir o que ainda não existe (offline, item 4).

Stack relevante: Expo SDK 57, React Native 0.86, `@react-native-async-storage/async-storage`
já declarado no `package.json`. Contratos em `mobile/src/contracts.ts`, cópia
fiel de `shared/ts/index.ts` (`snake_case` no fio).

## 2. `session_id` — AsyncStorage, sim

O `session_id` **não é segredo**: é um identificador de conversa, sem valor
para um atacante que não tenha também o token. AsyncStorage (texto plano) é o
lugar certo — usar armazenamento seguro aqui só adicionaria latência e
complexidade sem proteger nada.

Decisões, já refletidas no esqueleto de `storage.ts`:

- **Uma sessão por tela, com chaves separadas** (`shogun/chatSessionId` e
  `shogun/statusSessionId`). O chat é uma conversa contínua; a tela de status
  dispara sempre o mesmo comando e não deve poluir o histórico do chat, que o
  servidor concatena ao prompt (`SHOGUN_HISTORICO_MAX_MENSAGENS`).
- **Fluxo do contrato**: primeira mensagem sai com `session_id: null`; o
  servidor cria a sessão e devolve o id em `CommandResponse.session_id`; o
  cliente persiste e reenvia dali em diante. Persistir **sempre** o id que
  voltou na resposta (não só na primeira), para o caso de o servidor trocar o
  id no futuro.
- **"Nova conversa"**: ação explícita na tela de chat que apaga a chave e
  volta a mandar `null`. É a única forma de reset — o app nunca descarta a
  sessão sozinho.

## 3. Token — sair do AsyncStorage, ir para o SecureStore

Aqui o esqueleto atual precisa mudar antes de qualquer implementação:
`storage.ts` hoje guarda o token no AsyncStorage, que é **texto plano** no
filesystem do app (SQLite no Android, arquivos no iOS). Num aparelho com
backup habilitado ou root, o token vaza.

Plano:

- **Token** → `expo-secure-store` (Keychain no iOS, Keystore/EncryptedSharedPreferences
  no Android). O token do Shogun é pequeno (bem abaixo do limite de 2 KB do
  SecureStore) e é lido uma vez por requisição — o custo extra de leitura é
  irrelevante.
- **URL do servidor e `session_id`** permanecem no AsyncStorage: não são
  segredos, e o SecureStore não é feito para leitura frequente de dados
  não sensíveis.
- **Migração**: na primeira abertura da versão nova, se existir token no
  AsyncStorage, movê-lo para o SecureStore e apagar a chave antiga. Sem isso,
  quem já configurou o app teria que digitar o token de novo.
- O token continua saindo do aparelho **apenas** no header
  `Authorization: Bearer` — nunca em URL, log ou tela (o campo na Config
  exibe mascarado, com opção de revelar).

O transporte é HTTP puro dentro da tailnet (ver `server/README.md`, seção
Tailscale). O Tailscale cifra o túnel fim a fim, então não há token em claro
na rede — TLS no servidor fica fora do escopo deste plano, como já decidido.

## 4. Offline e falhas de rede

O celular é o cliente que mais vai estar longe do servidor: rede móvel,
Tailscale desligado, PC hibernando. Postura geral: **falhar rápido, explicar
bem, nunca reenviar sozinho**.

- **Sem fila de comandos offline.** Um assistente de voz que "guarda" comandos
  e os executa minutos depois, quando a rede volta, faz a coisa errada na
  maioria dos casos (a intenção era do momento). Comando que falhou por rede
  fica na tela como falho, com botão de **reenviar manual** — o texto digitado
  não se perde, mas a decisão de repetir é do usuário.
- **Detecção**: a falha do próprio `fetch` é a fonte da verdade (como no
  desktop). `expo-network`/NetInfo pode, num segundo momento, antecipar o
  aviso ("sem conexão") antes mesmo do fetch — é melhoria, não requisito.
- **Timeouts** (já no esqueleto, manter): 60 s no `POST /comando` (folga sobre
  os 30 s do `SHOGUN_LLM_TIMEOUT`, cobre modelo local frio + fallback) e curto
  (~4 s, espelhando o desktop) no `GET /health` da tela Config.
- **Nunca reenviar `POST /comando` automaticamente**: não é idempotente — cada
  tentativa grava mensagens na sessão e pode disparar ação de agente.
- **Histórico local**: as mensagens exibidas no chat são estado local. Persistir
  as últimas N no AsyncStorage para o app reabrir mostrando a conversa (o
  servidor guarda o histórico, mas não há endpoint de leitura hoje — quando
  houver, o local vira só cache).

## 5. O que espelhar do desktop (texto-primeiro)

O desktop está implementando agora a versão texto-primeiro; o mobile repete a
sequência — **primeiro digitar e ler, depois STT/TTS**. Do
`desktop/src/lib/api.ts` e `config.ts`, espelhar:

- **Texto antes de voz**: a tela de chat funciona completa por texto. STT/TTS
  entram depois, como camada sobre o mesmo `enviarComando` — a integração não
  muda.
- **Exibição de `actions`** como metadado da mensagem — detalhado no item 6.
- **Erros traduzidos para o usuário**, um tipo de erro único (`ApiError`, já
  no esqueleto, análogo ao `ErroComando` do desktop), com a causa crua indo
  para o console/log: 401/403 distingue "token recusado" de "token não
  configurado"; 503 explica que o LLM está indisponível e sugere tentar de
  novo; falha de rede aponta URL e Tailscale. A causa original nunca é
  engolida — foi lição aprendida no desktop.
- **Normalização de URL** (tirar barra final) na gravação, não em cada uso.
- **`/health` como teste de conexão** na tela Config (sem token, sem LLM),
  distinguindo "ninguém escutando", "respondeu mas com erro" e "ok".
- **Persistência do `session_id`** para sobreviver a reaberturas, com reset
  explícito (item 2).
- **Tema washi/sumi** com o mesmo mapa de tokens da identidade visual já
  aprovada (paleta washi do #16; bengara reservado a erro).

Diferenças conscientes em relação ao desktop: o RN usa o `fetch` nativo (sem
CORS, sem plugin), a config vive em AsyncStorage/SecureStore em vez do
tauri-plugin-store, e a URL default não existe — no celular não há
`localhost` útil, então a Config exige o IP Tailscale na primeira abertura.

## 6. `AgentAction` e `abrir_app` — o que o mobile faz com `actions`

Situação atual do contrato: `CommandResponse.actions` é **informativo**, não
executável. `AgentAction` carrega `agent`, `status` e `detail` (texto livre) —
nada que instrua o cliente a fazer algo. E `abrir_app` hoje é resolvido
inteiramente no servidor como placeholder (`server/app/api/comando.py`): a
resposta falada já diz "essa ação está em construção" e a action vem com
`status: "error"`. **Não há nada para o cliente executar hoje.**

O plano do mobile, portanto:

- **Renderizar `actions` como metadado discreto** da mensagem no chat (nome do
  agente + status + detail quando houver), com bengara reservado a
  `status: "error"`, seguindo a identidade visual. Nunca interpretar `detail`
  como instrução — é texto para humano.
- **`abrir_app` não entra em nenhum passo da ordem do item 7.** O TODO do
  servidor prevê delegar a execução ao cliente, mas esse contrato ainda não
  existe e a decisão é do servidor/`shared/` — quando for desenhado, precisará
  de um campo **estruturado** novo (ex.: uma instrução com o nome do app),
  porque extrair o alvo do `detail` por parsing seria acoplar o cliente a uma
  string de log.
- Registro antecipado da restrição do lado mobile, para quem for desenhar o
  contrato: no celular "abrir app" é deep link (`Linking.openURL`/`expo-linking`),
  e tanto o iOS (`LSApplicationQueriesSchemes`) quanto o Android 11+
  (`<queries>` no manifest) exigem declarar os schemes de antemão. Ou seja, o
  mobile só conseguirá abrir uma **lista curada** de apps conhecidos; alvo fora
  da lista vira resposta falada explicando que não dá. É diferente do desktop,
  que pode lançar processos arbitrários.

Nada disso bloqueia os passos 1–4 abaixo — a integração texto-primeiro
funciona por completo com `actions` apenas exibido.

## 7. Ordem de implementação proposta (pós-descongelamento)

1. **Token no SecureStore** com migração do AsyncStorage (item 3) — é correção
   do esqueleto, vem antes de qualquer feature.
2. **Chat texto-primeiro de ponta a ponta**: enviar, exibir resposta, persistir
   sessão, estados de erro do item 4.
3. **Tela Config**: URL + token (mascarado) + botão "testar conexão" via `/health`.
4. **Histórico local persistido** e reenviar manual.
5. **STT/TTS** — fora deste plano; não altera nada da integração acima.

Cada passo em branch própria a partir de `dev`, PR revisado, suíte verde —
nada disso começa sem o descongelamento explícito do mobile.
