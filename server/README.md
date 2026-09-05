# server

Servidor central do Shogun — Python 3.11+ com FastAPI.

Responsabilidades:
- expor a API (HTTP + WebSocket) consumida pelos clientes desktop e mobile;
- receber comandos já transcritos e interpretá-los via `LLMProvider` (Claude,
  DeepSeek, OpenAI ou modelo local no Ollama);
- orquestrar agentes especializados (`app/agents/`);
- manter contexto e memória da conversa.

## Rodando

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt   # ou requirements-dev.txt para rodar os testes
cp .env.example .env           # preencha a credencial do provedor escolhido
alembic upgrade head           # cria o banco (SQLite) na primeira vez
uvicorn app.main:app --reload  # desenvolvimento: 127.0.0.1:8000
```

O `--reload` do uvicorn escuta em `127.0.0.1` — bom para desenvolvimento, mas
invisível para outras máquinas. Para subir no host e na porta da configuração
(`SHOGUN_HOST`, `SHOGUN_PORT`), use o entrypoint do próprio servidor:

```bash
python -m app.main                # respeita SHOGUN_HOST / SHOGUN_PORT
```

ou passe as flags na mão:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Escutar na rede exige token

O servidor **recusa subir** quando o bind aceita conexões de outras máquinas
(qualquer host fora de `127.0.0.1`, `localhost` e `::1`) e `SHOGUN_AUTH_TOKEN`
está vazio. A falha é fatal, no startup, antes de a porta abrir — vale tanto
para `python -m app.main` quanto para `uvicorn app.main:app`:

```
ConfiguracaoInseguraError: o servidor vai escutar em 0.0.0.0, vindo de
uvicorn --host, o que aceita conexoes de outras maquinas - mas
SHOGUN_AUTH_TOKEN esta vazio, entao ele ficaria aberto a quem alcancasse a
porta. Defina SHOGUN_AUTH_TOKEN, ou escute em 127.0.0.1 para desenvolvimento
local sem token.
```

A mensagem diz de onde veio o host (`uvicorn --host`, `SHOGUN_HOST`, `--uds`,
`--fd`), para não confundir quem tem uma coisa no `.env` e outra na linha de
comando.

Em bind local o token continua **opcional**: só o próprio computador alcança o
servidor, e exigir token ali atrapalharia o desenvolvimento sem proteger nada.
Nesse caso sai apenas um aviso no log.

| Bind efetivo | Sem `SHOGUN_AUTH_TOKEN` | Com token |
|---|---|---|
| `127.0.0.1`, `localhost`, `::1` | sobe, com aviso no log | sobe |
| `0.0.0.0` ou qualquer IP | **recusa subir** | sobe |

#### O que é inspecionado: o bind real, não o `.env`

A verificação **não** lê `SHOGUN_HOST`. Ela lê o host que o servidor ASGI
realmente recebeu — `uvicorn --host 0.0.0.0` com `SHOGUN_HOST=127.0.0.1` no
`.env` é barrado do mesmo jeito, e o contrário (`--host 127.0.0.1` com
`SHOGUN_HOST=0.0.0.0`) sobe normalmente sem token.

O uvicorn não expõe essa informação à aplicação: não há hook de startup nem
campo no `scope` do lifespan com o host. O caminho usado está em
`app/core/rede.py` — o lifespan da app roda dentro da tarefa do
`uvicorn.lifespan.on.LifespanOn.main`, que é quem chama
`await app(scope, receive, send)`; esse frame carrega o `Config` do uvicorn, e é
de lá que o host é lido, percorrendo a pilha.

Isso acontece **antes do bind**: o uvicorn executa o lifespan e só depois abre o
socket (`Server.startup()` chama `lifespan.startup()` e em seguida
`loop.create_server(...)`). A recusa impede a porta de abrir — não fecha uma
porta que já abriu.

Casos de borda:

| Situação | Tratamento |
|---|---|
| `--host <ip>` / `uvicorn.run(host=...)` | usa esse host |
| `--uds /caminho.sock` | conta como local (só quem tem o filesystem alcança) |
| `--fd 3` | assume **exposto**: não dá para saber onde o descritor já escuta |
| fora do uvicorn (`TestClient`, outro servidor ASGI) | cai para `SHOGUN_HOST` |

A leitura depende de um detalhe interno do uvicorn (o nome do frame e o atributo
`config`). Se uma versão futura reorganizar isso, `descobrir_bind` volta ao
`SHOGUN_HOST` em vez de quebrar — e há teste subindo o uvicorn como processo de
verdade, justamente para que essa regressão apareça na suíte em vez de em
produção.

## Banco de dados

SQLite via SQLAlchemy — o banco é um arquivo, sem serviço para subir. Caminho em
`SHOGUN_DATABASE_URL` (default `sqlite:///./shogun.db`, relativo a `server/`).
O desenho do schema e as decisões estão em [`docs/DATABASE.md`](../docs/DATABASE.md).

Duas tabelas: `sessions` (uma conversa) e `messages` (uma fala, do Marcus ou do
Shogun). A ordenação canônica das mensagens é por `messages.id`, não por
`created_at`: duas mensagens gravadas no mesmo instante não teriam desempate por
timestamp, e a ordem user → assistant dentro de um comando precisa ser estável.

### Migrações

Alembic, com a revisão inicial já versionada. **O servidor não migra sozinho no
startup** — subir e migrar são operações diferentes:

```bash
alembic upgrade head            # aplica as migrações pendentes
alembic current                 # em que revisão o banco está
alembic downgrade -1            # volta uma
```

Depois de mexer nos modelos, gere a revisão e **leia o arquivo gerado** antes de
commitar — o autogenerate acerta o comum, não o sutil:

```bash
alembic revision --autogenerate -m "descricao curta"
```

A URL não fica no `alembic.ini`: `alembic/env.py` lê `SHOGUN_DATABASE_URL`, a
mesma variável do servidor. Duas fontes de verdade para o endereço do banco é
como se migra um banco e se roda contra outro.

### Sessão de conversa

`CommandRequest.session_id` é opcional. Nulo significa conversa nova: o servidor
cria a sessão e devolve o id em `CommandResponse.session_id`, que o cliente
guarda e reenvia nas próximas mensagens. Um id vindo do cliente também é aceito.

Antes de chamar o LLM, a rota lê as últimas `SHOGUN_HISTORICO_MAX_MENSAGENS`
mensagens da sessão e as concatena ao prompt como bloco de contexto — a
interface `LLMProvider` continua recebendo uma string só. O porquê e o gatilho
para mudar isso estão no passo 4 de [`docs/DESIGN.md`](../docs/DESIGN.md).

## Layout

```
app/
├── main.py     # entrypoint FastAPI
├── api/        # rotas HTTP e WebSocket
├── agents/     # agentes especializados
└── core/       # config, provedores de LLM, segurança, utilidades
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
| `conversar` | devolve a resposta livre do modelo |
| `consultar_pendencias` | consulta o `PendenciasProvider` injetado |
| `abrir_app` | placeholder — TODO, a execução caberá ao cliente |

### Injeção de dependências

O contrato `PendenciasProvider` (com `Pendencia` e `StatusAgente`) vive em
`app/domain/`. `app/core/pendencias.py` é apenas o ponto de injeção do FastAPI:
`get_pendencias_provider` devolve a implementação padrão
(`ShogunOrquestradorProvider`). Trocar para `MaestriProvider` quando a API existir
é mudar uma linha — nenhuma rota precisa mudar.

Em testes, sobrescreva com `app.dependency_overrides[get_pendencias_provider]`;
o mesmo vale para `get_llm_provider` e `get_settings`.

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
| `ollama` | `OllamaProvider` | `format` com JSON Schema (gramática, local) |

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

## Rodando local com Ollama

Para uso recorrente sem custo de API, o provedor `ollama` roda o modelo na sua
máquina. A recomendação é **não** usá-lo sozinho: deixe um provedor de nuvem como
fallback, porque um modelo 8B erra o formato com mais frequência que um modelo de
fronteira — e quando erra, o fallback responde em vez de o comando falhar.

### 1. Instalar o Ollama

| Sistema | Como |
| --- | --- |
| macOS / Windows | baixe o instalador em <https://ollama.com/download> |
| Linux | `curl -fsSL https://ollama.com/install.sh \| sh` |

O instalador já deixa o serviço rodando em `http://localhost:11434`. Para conferir:

```bash
curl http://localhost:11434/api/tags
```

### 2. Escolher e baixar o modelo

Não há modelo padrão: `OLLAMA_MODEL` é **obrigatória** quando o provedor `ollama`
é o principal ou o fallback. Sem ela, `OllamaProvider` nem chega a ser construído —
levanta `ConfiguracaoInvalidaError` na factory e o servidor não sobe, apontando esta
seção. Isso é deliberado: escolher o modelo tem consequência (VRAM, qualidade do
JSON), e um default silencioso esconderia a escolha. Quem roda com
`claude`/`deepseek`/`openai_mini` não precisa definir nada — a variável só é lida
quando o `ollama` está em uso.

Veja "Modelos candidatos" abaixo antes de escolher. Para baixar:

```bash
ollama pull <modelo>       # ex.: ollama pull qwen2.5:7b-instruct
```

Precisa de **Ollama 0.5+**: é a versão que aceita um JSON Schema no campo `format`.
Em versões anteriores só existe `"format": "json"`, que garante JSON sintaticamente
válido mas não impõe o schema — o provedor continua funcionando, porém a taxa de
resposta rejeitada na validação sobe bastante.

### Modelos candidatos

O papel aqui é estreito: **interpretador de comando**. O modelo não precisa
escrever bem nem saber muito — precisa acertar `ESQUEMA_COMANDO`
(`app/core/llm/base.py`), que é um schema **fechado**:

- `acao` restrito ao enum `conversar | consultar_pendencias | abrir_app`;
- `parametros` com `additionalProperties: false` e `required: ["app", "limite"]`
  — os dois campos são obrigatórios e anuláveis, ou seja, o modelo tem que emitir
  `null` explicitamente no que não se aplica, em vez de omitir a chave;
- `resposta_falada` em português do Brasil.

A gramática do Ollama garante a **forma** da saída, não a **semântica**: mesmo com
o schema aplicado, um modelo fraco escolhe a ação errada ou devolve uma
`resposta_falada` vazia ou em inglês. O que separa os candidatos é isso, mais o
comportamento sob decodificação restrita (alguns modelos degradam quando a
gramática corta os tokens que eles queriam emitir).

Números de VRAM são para os pesos em **Q4_K_M** (o default do `ollama pull`), sem
contar o contexto — reserve ~1 GB a mais. Rodar em CPU funciona, mas a primeira
chamada costuma estourar o `SHOGUN_LLM_TIMEOUT`.

| Modelo | Tamanho / VRAM | A favor | Contra |
| --- | --- | --- | --- |
| `qwen2.5:7b-instruct` | ~4,7 GB / ~6 GB | Dos 7B, o mais consistente em JSON estruturado e em respeitar enum; treinado com foco em tool/function calling. | Português do Brasil às vezes sai com cara de tradução na `resposta_falada`. |
| `llama3.1:8b` | ~4,9 GB / ~6 GB | Suporte oficial a tool calling; português decente; ecossistema e documentação amplos. | Tende a "explicar" fora do JSON quando o schema não é imposto — depende mais da gramática que os outros. |
| `hermes3:8b` | ~4,7 GB / ~6 GB | Fine-tune do Llama 3.1 voltado justamente a saída estruturada. | Herda os limites do 8B base; menos testado em português que o Llama upstream. |
| `mistral:7b-instruct` | ~4,4 GB / ~5,5 GB | O mais leve do grupo, rápido até em CPU; bom em línguas latinas. | O mais fraco em aderência a enum: erra a `acao` com mais frequência e cai no fallback. |
| `mistral-nemo:12b` | ~7,1 GB / ~9 GB | Salto real de qualidade sobre os 7B/8B mantendo VRAM de placa de 12 GB; contexto longo. | Já exige GPU dedicada; em CPU fica inviável para uso interativo. |
| `qwen2.5:14b-instruct` | ~9 GB / ~11 GB | Melhor combinação de JSON + semântica entre os que cabem em 12 GB; erra pouco a ação. | Precisa de 12 GB de VRAM com folga; primeira carga lenta. |
| `phi4:14b` | ~9,1 GB / ~11 GB | Muito bom em raciocínio para o tamanho; obedece instrução de formato. | Português é o ponto fraco — a `resposta_falada` costuma precisar de revisão. |
| `gemma2:9b` | ~5,4 GB / ~7 GB | Português mais natural na resposta falada. | Sem treino específico de tool calling; é o que mais depende da gramática para não fugir do schema. |

Regra prática para avaliar um candidato: rodar **com o fallback ligado** e com os
logs à vista. A frequência com que o fallback é acionado é a métrica que importa,
porque cada acionamento é um `LLMIndisponivelError` por JSON fora do schema.
Trocar de modelo é só `OLLAMA_MODEL` — nada no código muda.

### 3. Apontar o servidor para ele

```bash
SHOGUN_LLM_PROVIDER=ollama
SHOGUN_LLM_FALLBACK_PROVIDER=deepseek   # ou claude
OLLAMA_BASE_URL=http://localhost:11434  # default
OLLAMA_MODEL=qwen2.5:7b-instruct        # obrigatoria, sem default — escolha a sua
```

Nenhuma credencial é necessária para o Ollama — mas a do **fallback** sim, senão
ele falha junto e o erro cita os dois motivos.

### Notas de operação

- **Primeira chamada é lenta.** O modelo é carregado na memória sob demanda; em
  CPU isso passa fácil dos 30 s do `SHOGUN_LLM_TIMEOUT` e dispara o fallback sem
  necessidade. Ou suba o timeout, ou "aqueça" o modelo com um `ollama run
  <modelo> ""` antes de subir o servidor.
- **`SHOGUN_MAX_TOKENS` vira `num_predict`.** Vale para o modelo local o mesmo
  teto configurado para os outros provedores.
- **Ollama fora do ar não derruba a aplicação.** A falha de conexão vira
  `LLMIndisponivelError`, que é exatamente o que o `FallbackLLMProvider` trata.
  Sem fallback configurado, a rota devolve 503.
- **Trocar de modelo é só `OLLAMA_MODEL`** — veja "Modelos candidatos" acima, desde
  que o modelo suporte saída estruturada no Ollama.

## Acesso remoto via Tailscale

O cliente mobile não fica na mesma rede local que o PC. A ligação é feita pelo
Tailscale, que coloca os dois na mesma rede privada — o servidor não precisa ser
publicado na internet, e nenhuma porta é aberta no roteador.

### 1. Descobrir o IP Tailscale do PC

```bash
tailscale ip -4        # ex.: 100.101.102.103
```

Esse endereço é estável enquanto a máquina estiver na mesma tailnet. Os
`100.x.y.z` deste README são **exemplo** — use o que o comando devolver.

### 2. Subir o servidor escutando na rede

```bash
# .env
SHOGUN_HOST=0.0.0.0
SHOGUN_PORT=8000
SHOGUN_AUTH_TOKEN=<token-compartilhado-com-os-clientes>   # obrigatorio aqui
```

```bash
python -m app.main
```

Sem `SHOGUN_AUTH_TOKEN` o servidor recusa subir — ver
"Escutar na rede exige token", acima.

### 3. Apontar o cliente

Com o Tailscale ativo no celular, o servidor responde em:

```
http://100.101.102.103:8000
```

```bash
curl http://100.101.102.103:8000/health
# {"status":"ok"}
```

As requisições ao `/comando` continuam exigindo o header
`Authorization: Bearer <SHOGUN_AUTH_TOKEN>`, igual em rede local.

### Sobre segurança

O Tailscale já restringe o acesso à rede privada: só dispositivos da mesma
tailnet alcançam a porta. Somado ao Bearer token, é o suficiente por agora —
**não há autenticação adicional planejada** para este cenário.

Vale lembrar que `SHOGUN_HOST=0.0.0.0` escuta em *todas* as interfaces, não só
na do Tailscale. Numa rede Wi-Fi pública, a porta fica alcançável por quem
estiver na mesma rede — e é exatamente por isso que o token virou obrigatório
nesse modo.

### CORS

Não é necessário para os clientes atuais: desktop (Tauri) e mobile (React
Native) falam HTTP direto, sem origem de navegador, e não disparam preflight.
O `CORSMiddleware` só é registrado quando `SHOGUN_ALLOWED_ORIGINS` tem valor:

```bash
SHOGUN_ALLOWED_ORIGINS=http://100.101.102.103:8000,http://localhost:1420
```

Origens separadas por vírgula, nada hardcoded no código.

## Testes

```bash
pip install -r requirements-dev.txt
pytest            # a partir de server/
```

Nenhum teste chama API real: os provedores têm o cliente HTTP mockado e a rota usa
`app.dependency_overrides`.
