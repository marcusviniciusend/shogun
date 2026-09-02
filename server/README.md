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
pip install -r requirements.txt   # ou requirements-dev.txt para rodar os testes
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

## Provedores de LLM

A interpretação de comandos fica atrás da interface `LLMProvider`
(`app/core/llm/`), com um método único:

```python
async def interpretar_comando(self, texto: str) -> ComandoInterpretado
```

Todos os provedores compartilham a **mesma** personalidade (`SYSTEM_PROMPT`) e o
mesmo schema de saída (`acao`, `parametros`, `resposta_falada`) — trocar de LLM
não muda quem o Shogun é.

| `SHOGUN_LLM_PROVIDER` | Classe | Saída estruturada |
| --- | --- | --- |
| `claude` | `ClaudeProvider` | `output_config.format` (json_schema nativo) |
| `deepseek` | `DeepSeekProvider` | JSON mode + schema descrito no prompt |
| `openai_mini` | `OpenAIMiniProvider` | `response_format` json_schema `strict` |

### Adicionando um provedor

1. Crie a classe implementando `LLMProvider` (construtor recebe `Settings`).
2. Acrescente uma entrada em `PROVIDERS` (`app/core/llm/registry.py`).

Nada mais muda — nem a factory, nem as rotas.

### Fallback automático

`SHOGUN_LLM_FALLBACK_PROVIDER` envolve o principal em `FallbackLLMProvider`.
Se o principal levantar `LLMIndisponivelError` (timeout, rate limit, erro de API,
credencial ausente, resposta fora do formato), o reserva assume e o motivo da
troca vai para o log. Se ambos falharem, o erro propagado cita os dois motivos.
Vazio = sem fallback, erro propagado direto.

```bash
SHOGUN_LLM_PROVIDER=claude
SHOGUN_LLM_FALLBACK_PROVIDER=deepseek
```

Trocar de provedor ou ligar o fallback é só variável de ambiente — `api/comando.py`
recebe o provedor por `Depends(get_llm_provider)` e não conhece nenhuma implementação.

## Testes

```bash
pip install -r requirements-dev.txt
pytest            # a partir de server/
```

Nenhum teste chama API real: os provedores têm o cliente HTTP mockado e a rota usa
`app.dependency_overrides`.
