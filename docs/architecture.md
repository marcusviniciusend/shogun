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
| [ROADMAP.md](ROADMAP.md) | Planejamento por fases: v1.0 do desktop, backlog do mobile, ideias futuras |
| [CONTEXTO-GERAL.md](CONTEXTO-GERAL.md) | Ponto único de entrada para recuperar o contexto do projeto numa sessão nova |

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

- Onde roda o STT: a intenção é no cliente (menor latência, mais peso no app);
  a alternativa é no servidor (clientes mais simples, mais tráfego). STT ficou
  para a v1.1 — hoje a entrada é por texto.
- Formato da memória de longo prazo, além do histórico bruto de mensagens — é
  um dos gatilhos de migração para Postgres em [DATABASE.md](DATABASE.md).
- Streaming da resposta: SSE ou WebSocket, e como conciliar com a saída
  estruturada dos provedores. Ver [DESIGN.md](DESIGN.md) — aguardando documento
  de design antes de implementar.

Já decididos:

- autenticação por Bearer token fixo (`SHOGUN_AUTH_TOKEN`), com rate limit por
  token (429 + `Retry-After`);
- persistência em SQLite via SQLAlchemy ([DATABASE.md](DATABASE.md));
- **TTS no cliente**: o desktop sintetiza com o `speechSynthesis` nativo do
  WebView2 (voz do próprio Windows, zero dependência e zero chave de API);
  motor de voz natural fica como upgrade futuro atrás da mesma interface
  (`desktop/src/lib/voz.ts`);
- **contrato de `abrir_app`**: o servidor delega via `ClientInstruction`
  (`shared/`) mandando só o nome do app; o cliente executa a partir de uma
  lista curada e responde com `fallback_text` quando não suporta. O desktop já
  executa; no mobile fica para o pós-descongelamento.
