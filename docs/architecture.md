# Arquitetura do Shogun

## Visão geral

O Shogun é dividido entre um **servidor central** (o "cérebro") e **clientes finos**
(desktop e mobile). Os clientes capturam voz, exibem a interface e reproduzem a
resposta; toda a inteligência, memória e orquestração ficam no servidor.

```
  ┌────────────┐        ┌────────────┐
  │  desktop   │        │   mobile   │
  │  (Tauri)   │        │    (RN)    │
  └─────┬──────┘        └─────┬──────┘
        │      WebSocket / HTTP      │
        └──────────┬─────────────────┘
                   ▼
            ┌─────────────┐      ┌──────────────┐
            │   server    │─────▶│  API Claude  │
            │  (FastAPI)  │      └──────────────┘
            │             │
            │  orquestrador
            │   ├── agente de sistema
            │   ├── agente de agenda
            │   └── agente de busca
            └─────────────┘
```

## Fluxo de um comando

1. O cliente detecta o acionamento (hotkey, botão ou wake word) e captura o áudio.
2. O áudio é transcrito (STT) e o texto é enviado ao servidor como `CommandRequest`.
3. O orquestrador monta o contexto da sessão e chama a API da Claude.
4. Se a resposta indicar uso de ferramentas, o orquestrador aciona os agentes
   correspondentes e devolve os resultados ao modelo.
5. A resposta final volta ao cliente como `CommandResponse`.
6. O cliente exibe o texto e o sintetiza em voz (TTS).

## Componentes

### server (Python + FastAPI)
Ponto único de entrada. Expõe HTTP para operações pontuais e WebSocket para a
conversa em streaming. Guarda o histórico e a memória de longo prazo das sessões.

### desktop (Tauri)
Frontend web empacotado em binário nativo com backend em Rust — usado para hotkey
global, acesso ao áudio e integração com o sistema operacional.

### mobile (React Native)
Cliente para celular, com push-to-talk e conversa em tempo real pelo mesmo protocolo
WebSocket.

### shared
Contratos em JSON Schema como fonte da verdade, com tipos TypeScript e modelos
Pydantic derivados, garantindo que servidor e clientes falem a mesma língua.

## Decisões em aberto

- Onde roda o STT: no cliente (menor latência, mais peso no app) ou no servidor
  (clientes mais simples, mais tráfego).
- Motor de TTS e se a voz é sintetizada no cliente ou no servidor.
- Estratégia de autenticação entre clientes e servidor.
- Formato da memória de longo prazo (arquivo, SQLite ou banco vetorial).
