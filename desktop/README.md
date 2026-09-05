# desktop

Aplicativo desktop do Shogun — [Tauri 2](https://tauri.app) (Rust) com frontend
em React + TypeScript (Vite).

Responsabilidades (visão completa; nem tudo existe ainda):
- captura de áudio e hotkey global para acionar o assistente (a construir);
- interface para conversar com o `server/` e acompanhar os agentes (**feito**);
- reprodução da resposta em voz (a construir);
- comunicação com o `server/` — hoje via `POST /comando`; WebSocket depois.

## O que o scaffold atual faz

Dashboard com três áreas:

- **Conversa** — histórico usuário/Shogun, campo de texto e envio ao
  `POST /comando`. O `session_id` devolvido pelo servidor é persistido
  localmente e reenviado nas próximas mensagens; "Nova conversa" descarta a
  sessão. Enquanto o servidor pensa, aparece um estado de carregamento (a
  primeira resposta pode demorar, especialmente com Ollama frio).
- **Agentes** — painel de status alimentado pela ação `consultar_pendencias`.
  O refresh é **manual** (botão "Atualizar"), que envia o comando fixo
  "ver pendências dos agentes". Escolhemos manual em vez de polling porque
  cada consulta passa pelo LLM: um polling periódico gastaria chamadas sem
  ninguém olhando. Quando existir um endpoint direto de pendências, vale
  revisitar.
- **Configurações** — URL do servidor (default `http://localhost:8000`,
  editável para um IP Tailscale) e Bearer token (`SHOGUN_AUTH_TOKEN`). Nada é
  hardcoded: os valores ficam num store local do Tauri
  (`tauri-plugin-store`, arquivo `shogun.json` no diretório de dados do app),
  junto com o `session_id` corrente.

Erros são exibidos ao usuário com mensagem específica: servidor fora do ar,
token recusado (401/403) e provedor de LLM indisponível (503).

As chamadas HTTP saem pelo `tauri-plugin-http` (fetch via Rust), não pelo
fetch do webview — assim não há CORS e o servidor não precisa de
`SHOGUN_ALLOWED_ORIGINS`, seja em localhost ou via Tailscale.

Nota sobre contratos: `shared/ts/index.ts` declara os campos em camelCase
(`sessionId`), mas o JSON real do servidor (Pydantic, sem alias) é snake_case
(`session_id`). Até o contrato compartilhado ser alinhado, o desktop usa tipos
locais em `src/lib/types.ts` que espelham o fio de verdade.

## Identidade visual e animações

O redesenho segue minimalismo japonês ("ma"), na paleta "washi cru": fundo
de papel claro (`#EDE6D4`), tinta sumi para texto e para o pincel do kanji
(`#211E1A`), cinza *hai* para o secundário (`#7A7264`), e o bengara
(`#A63D2F`) reservado **exclusivamente** a erro e atenção crítica — nunca
decorativo. Tipografia como voz — o Shogun fala em Zen Old Mincho
(serifa), o usuário e os controles em Zen Kaku Gothic New. Fontes
embarcadas via fontsource, nada vem da rede.

Duas animações usam o kanji 将軍 escrito a pincel (WebM com canal alpha em
`src/assets/`, renderizados com Remotion a partir de um projeto separado,
fora deste repositório):

- **splash de abertura** — o kanji é escrito traço a traço, sustentado e
  desfeito (~5,6s); um clique pula. `src/components/Splash.tsx`;
- **wordmark vivo** — o kanji do cabeçalho é a versão condensada sendo
  escrita em loop contínuo (2,2s), o tempo todo, não só durante o
  processamento.

Com `prefers-reduced-motion`, nem o splash nem os vídeos montam.

A navegação vive numa barra lateral fina à esquerda (só ícones; expande no
hover ou foco): nova conversa, Conversa, Agentes, visualização dividida e
Configurações. Por padrão cada view ocupa a tela sozinha; o modo dividido
(chat + agentes lado a lado) é um toggle com ícone próprio na sidebar —
preferido a uma opção nas configurações por ficar visível, custar um
clique e mostrar o estado ativo no próprio ícone. Clicar em Conversa ou
Agentes com o dividido ativo volta para a view única daquele item.

Os traços do kanji vêm do projeto [KanjiVG](http://kanjivg.tagaini.net)
(Ulrich Apel), licença CC BY-SA 3.0 — atribuição obrigatória mantida aqui.

## Estrutura

```
src/
├── App.tsx               # layout do dashboard e estado principal
├── components/
│   ├── Chat.tsx          # histórico + campo de comando
│   ├── PainelAgentes.tsx # status dos agentes (refresh manual)
│   └── Configuracoes.tsx # URL do servidor + token
└── lib/
    ├── api.ts            # POST /comando + tradução de erros
    ├── config.ts         # persistência local (tauri-plugin-store)
    └── types.ts          # tipos do fio do /comando
src-tauri/                # shell Rust (plugins http e store, sem comando custom)
```

## Rodando

Pré-requisitos: Node.js 20+, Rust (rustup) e as
[dependências de sistema do Tauri](https://tauri.app/start/prerequisites/).

```bash
cd desktop
npm install
npm run tauri dev
```

Suba o `server/` antes (veja `server/README.md`) e aponte a URL e o token na
tela de configurações do app.

Build de distribuição: `npm run tauri build`.
