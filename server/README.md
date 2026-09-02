# server

Servidor central do Shogun — Python 3.11+ com FastAPI.

Responsabilidades:
- expor a API (HTTP + WebSocket) consumida pelos clientes desktop e mobile;
- transcrever/receber comandos e enviá-los à API da Claude;
- orquestrar agentes especializados (`app/agents/`);
- manter contexto e memória da conversa.

## Rodando

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env           # preencha ANTHROPIC_API_KEY
uvicorn app.main:app --reload
```

## Layout

```
app/
├── main.py     # entrypoint FastAPI
├── api/        # rotas HTTP e WebSocket
├── agents/     # agentes especializados
└── core/       # config, cliente Claude, utilidades
```

## API

### `POST /comando`

Recebe o texto **já transcrito** pelo cliente e devolve a resposta falada mais as
ações executadas. Autenticação por Bearer token fixo (`SHOGUN_AUTH_TOKEN`).

```bash
curl -X POST http://localhost:8000/comando \
  -H "Authorization: Bearer $SHOGUN_AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"session_id":"s1","text":"o que tenho pendente hoje?","client":"desktop"}'
```

```json
{
  "session_id": "s1",
  "text": "Você tem 2 pendências: Assinar contrato (até sexta); Ligar pro contador.",
  "actions": [{ "agent": "pendencias", "status": "ok", "detail": "2 pendências" }]
}
```

Contratos (`CommandRequest` / `CommandResponse`) vêm de `shared/python`.

### Ações suportadas

| ação | comportamento |
| --- | --- |
| `conversar` | devolve a resposta livre da Claude |
| `consultar_pendencias` | consulta o `PendenciasProvider` injetado |
| `abrir_app` | placeholder — TODO, a execução caberá ao cliente |

### Injeção de dependências

`app/core/pendencias.py` define uma interface **temporária** (`PendenciasProvider`)
com a assinatura assumida `async listar_pendencias(limite: int)`. Enquanto o módulo
de domínio do `agente-contratos` não existir, `get_pendencias_provider` devolve um
stub vazio. No merge, troque o retorno dessa função pelo provedor real — nenhuma
rota precisa mudar.

Em testes, sobrescreva com `app.dependency_overrides[get_pendencias_provider]`;
o mesmo vale para `get_claude_client` e `get_settings`.
