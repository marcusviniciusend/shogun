# Arquitetura do Shogun

Índice da documentação técnica. O detalhe vive nos documentos temáticos; esta
página só dá a visão geral e aponta para eles.

## Visão geral

O Shogun é dividido entre um **servidor central** (o "cérebro") e **clientes
finos** (desktop e mobile). Os clientes capturam voz, exibem a interface e
reproduzem a resposta; toda a inteligência, memória e orquestração ficam no
servidor.

```
  ┌────────────┐        ┌────────────┐
  │  desktop   │        │   mobile   │
  │  (Tauri)   │        │    (RN)    │
  └─────┬──────┘        └─────┬──────┘
        │      WebSocket / HTTP      │
        └──────────┬─────────────────┘
                   ▼
            ┌─────────────┐      ┌──────────────────────────────────┐
            │   server    │─────▶│           LLM Provider           │
            │  (FastAPI)  │      │ Claude | DeepSeek | GPT-4o mini  │
            │             │      │      | Ollama/Hermes (local)     │
            │ orquestrador│      │     com fallback automático      │
            │  ├── sistema│      └──────────────────────────────────┘
            │  ├── agenda │
            │  └── busca  │
            └─────────────┘
```

## Documentos

| Documento | Sobre |
| --- | --- |
| [DESIGN.md](DESIGN.md) | O caminho completo de uma mensagem, passo a passo, marcando o que já existe e o que falta |
| [DATABASE.md](DATABASE.md) | Schema de sessões e histórico em SQLite/SQLAlchemy, e os critérios para migrar a Postgres |
| [AGENTS.md](AGENTS.md) | O papel de `server/app/agents/` e a distinção entre agentes do Shogun e agentes do Maestri |

Fora de `docs/`: [`server/README.md`](../server/README.md) tem a configuração dos
provedores de LLM e como rodar o modelo local com Ollama.

## Componentes

| Componente | Papel |
| --- | --- |
| `server/` (Python + FastAPI) | Ponto único de entrada. HTTP para operações pontuais, WebSocket para conversa em streaming. Guarda histórico e memória de longo prazo. |
| `desktop/` (Tauri) | Frontend web em binário nativo com backend Rust — hotkey global, áudio e integração com o SO. |
| `mobile/` (React Native) | Push-to-talk e conversa em tempo real pelo mesmo protocolo. |
| `shared/` | Contratos como fonte da verdade, com tipos TypeScript e modelos Pydantic derivados — servidor e clientes falam a mesma língua. |

## Decisões em aberto

- Onde roda o STT: hoje no cliente (menor latência, mais peso no app); a
  alternativa é no servidor (clientes mais simples, mais tráfego).
- Motor de TTS e se a voz é sintetizada no cliente ou no servidor.
- Contrato de `abrir_app` entre servidor e cliente — o servidor não tem acesso ao
  SO do Marcus. Ver [AGENTS.md](AGENTS.md).
- Formato da memória de longo prazo, além do histórico bruto de mensagens — é
  um dos gatilhos de migração para Postgres em [DATABASE.md](DATABASE.md).
- Streaming da resposta: SSE ou WebSocket, e como conciliar com a saída
  estruturada dos provedores. Ver [DESIGN.md](DESIGN.md).

Já decididos: autenticação por Bearer token fixo (`SHOGUN_AUTH_TOKEN`);
persistência em SQLite via SQLAlchemy ([DATABASE.md](DATABASE.md)).
