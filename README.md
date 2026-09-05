# Shogun

**Um comandante digital** — assistente pessoal de voz, para Desktop e Mobile.

Shogun escuta comandos de voz, entende a intenção com um modelo de linguagem — na
nuvem ou rodando na sua própria máquina — e executa ações: consultar informações,
controlar o computador, orquestrar agentes especializados e responder por voz.

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
            ┌─────────────┐      ┌──────────────────────────────────┐
            │   server    │─────▶│           LLM Provider           │
            │  (FastAPI)  │      │ Claude | DeepSeek | GPT-4o mini  │
            │  agentes    │      │      | Ollama/Hermes (local)     │
            └─────────────┘      │     com fallback automático      │
                                 └──────────────────────────────────┘
```

## Estrutura do monorepo

| Diretório  | Descrição |
|------------|-----------|
| `server/`  | Servidor central em Python + FastAPI. Recebe comandos, consulta o provedor de LLM configurado e orquestra os agentes. |
| `desktop/` | Aplicativo desktop em Tauri (Rust + JS/TS). |
| `mobile/`  | Aplicativo mobile em React Native. |
| `shared/`  | Tipos e contratos compartilhados entre servidor e clientes. |
| `docs/`    | Documentação de arquitetura e decisões técnicas. |

## Provedores de LLM

O Shogun não está preso a um único fornecedor de IA. O servidor conversa com os
modelos através da abstração `LLMProvider`: todos compartilham a mesma
personalidade e o mesmo contrato de saída, então **trocar de modelo não muda
quem o Shogun é** — muda apenas quanto custa e onde ele roda.

| `SHOGUN_LLM_PROVIDER` | Modelo | Observação |
| --- | --- | --- |
| `claude` | Claude (Anthropic) | maior qualidade de interpretação |
| `deepseek` | DeepSeek | alternativa de nuvem mais barata |
| `openai_mini` | GPT-4o mini (OpenAI) | alternativa de nuvem mais barata |
| `ollama` | Hermes 3 8B via [Ollama](https://ollama.com/) | roda local, sem custo de API |

`SHOGUN_LLM_FALLBACK_PROVIDER` define um segundo provedor que assume
automaticamente quando o principal falha — serviço fora do ar, timeout, rate
limit, credencial ausente ou resposta fora do formato esperado. É o que torna
o modelo local viável no dia a dia: com `ollama` como principal e um provedor
de nuvem como reserva, o uso recorrente não custa nada e o comando continua
funcionando mesmo com o Ollama desligado.

```bash
SHOGUN_LLM_PROVIDER=ollama
SHOGUN_LLM_FALLBACK_PROVIDER=deepseek
```

Detalhes de cada provedor, configuração e instalação do Ollama estão em
[`server/README.md`](server/README.md).

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
