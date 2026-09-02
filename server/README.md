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
