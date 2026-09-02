# desktop

Aplicativo desktop do Shogun — [Tauri](https://tauri.app) (Rust) com frontend em JS/TS.

Responsabilidades:
- captura de áudio e hotkey global para acionar o assistente;
- interface (overlay/HUD) para exibir a conversa;
- reprodução da resposta em voz;
- comunicação com o `server/` via WebSocket.

## Setup

Ainda não inicializado. Para criar o projeto:

```bash
npm create tauri-app@latest .
npm install
npm run tauri dev
```

Pré-requisitos: Node.js 20+, Rust (rustup) e as
[dependências de sistema do Tauri](https://tauri.app/start/prerequisites/).
