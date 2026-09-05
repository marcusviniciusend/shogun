# mobile

> ## ⏸️ Em backlog
>
> **Decisão do Marcus, 2026-09-05: nenhum trabalho novo aqui até o desktop
> chegar a uma versão 1.0.** O scaffold está mergeado e passa em
> `tsc --noEmit`; fica parado onde está.
>
> **Ao retomar, isto não está pronto sem alcançar o patamar de resiliência do
> desktop.** O que falta, concretamente:
>
> - `src/api.ts` captura a exceção e trata timeout, mas **não registra a causa
>   crua** e agrupa todo o resto numa frase só — porta sem ninguém escutando,
>   DNS e rota morta ficam indistinguíveis;
> - `verificarSaude()` (`GET /health`) existe, mas só é chamada **manualmente**
>   no botão "testar conexão" da aba Config. O chat e a aba Status continuam
>   descobrindo que o servidor caiu gastando uma chamada de LLM;
> - não há indicador visível de "servidor não alcançado" nas telas de uso.
>
> Do lado bom: o timeout de 60 s com `AbortController` daqui é justamente o que
> o **desktop** ainda não tem.
>
> Detalhes em `.maestri/levantamento-resiliencia-desktop.md` e na seção 1.3 de
> `docs/CONTEXTO-GERAL.md`.

Aplicativo mobile do Shogun — React Native com Expo (TypeScript).

Responsabilidades:
- captura de voz no celular (push-to-talk / wake word) — **a construir**;
- interface de conversa;
- reprodução da resposta em voz (TTS) — **a construir**;
- comunicação com o `server/` via HTTP (`POST /comando`); WebSocket é evolução
  futura.

## Estado atual

Scaffold funcional com três abas:

| Aba | O que faz |
| --- | --- |
| **Chat** | Conversa por texto com o servidor. O `session_id` devolvido pelo servidor é persistido localmente (AsyncStorage) e reenviado — a conversa continua entre aberturas do app. O histórico exibido também fica no aparelho. |
| **Status** | Consulta as pendências dos agentes enviando um comando à ação `consultar_pendencias`, numa sessão própria, separada da do chat. |
| **Config** | URL do servidor e token de acesso, salvos só no aparelho — nada hardcoded. Botão de testar conexão via `GET /health`. |

Contratos da API em `src/contracts.ts` — espelham `shared/python/__init__.py`
(snake_case, o formato que realmente trafega; ver nota no próprio arquivo sobre
a divergência com `shared/ts`).

## Setup

Pré-requisitos: Node.js 20+ e, para rodar no aparelho, o app **Expo Go**
(ou Android Studio / Xcode para builds nativos).

```bash
cd mobile
npm install
npm run start        # abre o Metro; escaneie o QR code com o Expo Go
```

## Conectando ao servidor

O celular normalmente não está na mesma rede local que o PC — a ligação é pelo
**Tailscale** (ver "Acesso remoto via Tailscale" em `server/README.md`):

1. no PC, suba o servidor escutando na rede (`SHOGUN_HOST=0.0.0.0` +
   `SHOGUN_AUTH_TOKEN` obrigatório) e descubra o IP com `tailscale ip -4`;
2. no celular, com o Tailscale ativo, abra a aba **Config** e preencha:
   - URL: `http://100.x.x.x:8000` (o IP que o comando devolveu);
   - token: o mesmo `SHOGUN_AUTH_TOKEN` do servidor;
3. toque em **Testar conexão** — deve responder que o `/health` está ok.

URL e token ficam apenas no AsyncStorage do aparelho.

## Layout

```
App.tsx              # abas (Chat | Status | Config) por estado local, sem lib de rotas
src/
├── contracts.ts     # tipos do fio (CommandRequest/CommandResponse, snake_case)
├── api.ts           # cliente HTTP: /comando e /health, erros viram ApiError
├── storage.ts       # AsyncStorage: config do servidor e ids de sessão
├── theme.ts         # paleta e espaçamentos
├── components/      # Aviso (banner de erro)
└── screens/         # ChatScreen, StatusScreen, ConfigScreen
```
