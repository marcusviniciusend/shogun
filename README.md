# Shogun

**Um comandante digital** — assistente pessoal de voz, para Desktop e Mobile.

Shogun escuta comandos de voz, entende a intenção com a API da Claude (Anthropic) e
executa ações: consultar informações, controlar o computador, orquestrar agentes
especializados e responder por voz.

## Propósito

A ideia é ter um único "cérebro" (o servidor) acessível a partir de qualquer cliente —
o desktop, o celular ou, no futuro, outros dispositivos. Os clientes cuidam apenas de
capturar áudio, exibir a interface e reproduzir a resposta; toda a inteligência,
memória e orquestração ficam centralizadas no servidor.

```
  ┌────────────┐        ┌────────────┐
  │  desktop   │        │   mobile   │
  │  (Tauri)   │        │   (RN)     │
  └─────┬──────┘        └─────┬──────┘
        │      WebSocket / HTTP      │
        └──────────┬─────────────────┘
                   ▼
            ┌─────────────┐      ┌──────────────┐
            │   server    │─────▶│  API Claude  │
            │  (FastAPI)  │      └──────────────┘
            │  agentes    │
            └─────────────┘
```

## Estrutura do monorepo

| Diretório  | Descrição |
|------------|-----------|
| `server/`  | Servidor central em Python + FastAPI. Recebe comandos, chama a API da Claude e orquestra os agentes. |
| `desktop/` | Aplicativo desktop em Tauri (Rust + JS/TS). |
| `mobile/`  | Aplicativo mobile em React Native. |
| `shared/`  | Tipos e contratos compartilhados entre servidor e clientes. |
| `docs/`    | Documentação de arquitetura e decisões técnicas. |

## Status

Projeto em fase inicial — a estrutura está sendo montada. Consulte
[`docs/architecture.md`](docs/architecture.md) para a visão geral da arquitetura.

## Começando

```bash
# servidor
cd server
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Cada subprojeto tem seu próprio `README.md` com instruções específicas.

## Licença

[AGPL-3.0](LICENSE) © marcusviniciusend
