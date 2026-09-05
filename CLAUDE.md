# Shogun — guia de contexto para o Claude Code

Este arquivo é lido automaticamente pelo Claude Code no início de cada sessão neste
repositório. Ele vale para todos os agentes que trabalham aqui — leia antes de mexer
em qualquer coisa.

## 1. Visão geral

Shogun é um assistente pessoal de voz (estilo JARVIS) para desktop e mobile.

O desenho é **um cérebro, vários clientes**: um servidor central concentra
inteligência, memória e orquestração; os clientes só capturam áudio, mostram a
interface e reproduzem a resposta.

Fluxo de um comando:

1. o cliente captura o áudio e transcreve (STT no cliente, hoje);
2. envia o texto ao servidor como `CommandRequest` (`POST /comando`, Bearer token);
3. o servidor interpreta a intenção via `LLMProvider` e devolve
   `{acao, parametros, resposta_falada}`;
4. conforme a ação, o servidor consulta os provedores/agentes internos;
5. o cliente recebe `CommandResponse` e sintetiza a resposta em voz (TTS).

Detalhes de arquitetura e decisões em aberto: [`docs/architecture.md`](docs/architecture.md).
Detalhes do servidor (endpoints, env vars, provedores): [`server/README.md`](server/README.md).

## 2. Arquitetura atual

Monorepo, sem empacotamento (não há `pyproject.toml` instalável — o `sys.path` é
ajustado em `server/app/core/contracts.py` e em `server/tests/conftest.py`).

| Diretório  | O que é |
|------------|---------|
| `server/`  | Servidor central: Python 3.11+ e FastAPI. Único componente com lógica real hoje. |
| `desktop/` | Cliente Tauri (Rust + JS/TS). Ainda só o README. |
| `mobile/`  | Cliente React Native. Ainda só o README. |
| `shared/`  | Contratos compartilhados (`CommandRequest`, `CommandResponse`, `AgentAction`) — Pydantic em `shared/python`, TS em `shared/ts`. |
| `docs/`    | Arquitetura e decisões técnicas. |

### Servidor (`server/app/`)

```
main.py             # entrypoint FastAPI (/health + router de comando)
api/                # rotas HTTP/WebSocket — comando.py
core/
  config.py         # Settings (pydantic-settings, lê .env)
  contracts.py      # ponte para shared/python
  security.py       # autenticação Bearer
  pendencias.py     # ponto de injeção do PendenciasProvider no FastAPI
  llm/              # abstração de LLM (base, registry, fallback, provedores)
domain/             # domínio puro — sem HTTP, sem FastAPI
  pendencias.py     # StatusAgente, Pendencia, PendenciasProvider (ABC)
  providers/        # MaestriProvider, ShogunOrquestradorProvider
agents/             # agentes especializados (a construir)
```

Regra de dependência: `domain/` não importa nada de `api/` nem do FastAPI. A rota
depende da **interface**, nunca de uma implementação concreta — a troca acontece na
injeção de dependência (`app.dependency_overrides` nos testes).

### Abstração de LLM

A interpretação de comandos fica atrás de `LLMProvider` (`server/app/core/llm/base.py`),
um `Protocol` com um método: `async interpretar_comando(texto) -> ComandoInterpretado`.

- `SYSTEM_PROMPT` e `ESQUEMA_COMANDO` são **compartilhados por todos os provedores** —
  trocar de LLM não muda quem o Shogun é.
- Toda falha (rede, timeout, rate limit, resposta fora do formato) vira
  `LLMIndisponivelError`. É o erro que a rota trata e o que dispara o fallback.
- `PROVIDERS` (`core/llm/registry.py`) mapeia nome de configuração → classe:
  `claude` (`ClaudeProvider`), `deepseek` e `openai_mini` (`openai_compat.py`) e
  `ollama` (`OllamaProvider`, `core/llm/ollama.py`) — provedor local, já
  implementado, registrado em `PROVIDERS` e coberto por testes.
- `FallbackLLMProvider` envolve o principal quando `SHOGUN_LLM_FALLBACK_PROVIDER`
  está preenchido: o reserva assume se o principal levantar `LLMIndisponivelError`.

Escolher provedor e fallback é só variável de ambiente — nenhuma rota conhece
implementação concreta.

## 3. Convenções

### Branches

- **A branch de trabalho é sempre `dev`.** Nunca commitar direto em `main`.
- Trabalho novo sai de `dev`, em `feature/<assunto>`.
- `main` é integrada só via PR revisado.

### Commits

- Conventional commits, em português, sem acentos na mensagem (o histórico segue
  esse padrão): `feat(server): ...`, `fix(server): ...`, `docs(server): ...`,
  `chore(repo): ...`, `test(server): ...`.
- **Um commit por escopo.** Não misturar código, teste e documentação num commit só.
- Cada commit precisa ser **funcional isoladamente**: a suíte passa em qualquer
  ponto do histórico, não só no final da série.

### Testes

- `pytest`, a partir de `server/` (config em `server/pytest.ini`, `asyncio_mode = auto`).
  Dependências em `server/requirements-dev.txt`.
- **Nenhum teste chama API real.** Provedores têm o cliente HTTP mockado; as rotas
  usam `app.dependency_overrides` (`get_llm_provider`, `get_pendencias_provider`,
  `get_settings`). Fixtures compartilhadas em `server/tests/conftest.py`.
- **Rodar a suíte completa antes de considerar qualquer tarefa concluída** — não
  apenas o arquivo de teste que você mexeu.

```bash
cd server
pip install -r requirements-dev.txt
pytest
```

### Onde colocar código novo

- **Contratos e interfaces de domínio** → `server/app/domain/`. Domínio puro:
  Pydantic/ABC, sem FastAPI, sem HTTP, sem I/O direto na interface.
- **Implementações de `PendenciasProvider`** → `server/app/domain/providers/`.
- **Novo provedor de LLM** → `server/app/core/llm/`, seguindo o padrão já
  estabelecido: classe que implementa o `Protocol` `LLMProvider`, construtor
  recebendo `Settings`, e uma entrada nova em `PROVIDERS` (`registry.py`). Nada
  mais muda — nem a factory, nem as rotas.
- **Rotas e configuração** → `server/app/api/` e `server/app/core/`.
- **Contrato usado também pelos clientes** → `shared/`.

## 4. Fluxo de trabalho esperado

1. criar a branch a partir de `dev` (`git checkout dev && git checkout -b feature/<assunto>`);
2. implementar;
3. testar — suíte completa verde;
4. commitar em commits atômicos, separados por escopo e funcionais isoladamente;
5. `git push -u origin feature/<assunto>`;
6. **parar aqui. NÃO abrir PR automaticamente.**

O PR é aberto manualmente pelo humano. **Revisão humana é obrigatória antes de
qualquer merge** — nenhum agente faz merge.

## 5. Áreas de responsabilidade

Divisão usada entre os agentes do projeto; serve de referência de contexto entre
sessões.

| Área | Onde vive | Conteúdo |
|------|-----------|----------|
| Domínio / Contratos | `server/app/domain/` | `PendenciasProvider` (ABC), `StatusAgente`, `Pendencia`, e as implementações `MaestriProvider` (placeholder da API do Maestri, ainda indefinida) e `ShogunOrquestradorProvider` (implementação própria, hoje em memória). |
| Backend / API | `server/app/api/`, `server/app/core/` | Rotas (`/comando`, `/health`), autenticação, `Settings`, provedores de LLM e fallback. |
| Testes | `server/tests/` | `test_domain.py`, `test_comando.py`, `test_llm.py` e as fixtures de `conftest.py`. |

Quem trabalha no domínio não mexe em rotas; quem trabalha nas rotas consome a
interface, não a implementação.

## 6. ⚠️ Branch default do GitHub está errada

O repositório está com a branch default configurada como **`main`** no GitHub, mas a
branch de integração do projeto é **`dev`**.

Enquanto isso não for corrigido nas configurações do repositório, **todo PR nasce
apontando para `main` e a base precisa ser trocada manualmente para `dev`** antes de
qualquer revisão. Conferir isso é parte da abertura do PR.
