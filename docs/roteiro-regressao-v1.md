# Roteiro de regressão manual — desktop v1.0

Roteiro de conferência do cliente desktop antes de fechar a v1.0. Existe porque
a suíte automatizada cobre o servidor (231 testes) e **nada** do cliente: no
desktop, o que roda sem humano é compilação de tipos (`tsc`) e de Rust
(`cargo`). Todo comportamento — bolha de erro, voz, app abrindo, refresh do
painel — só se verifica com o app na tela.

Cada item tem **passo**, **resultado esperado** e **onde olhar quando falhar**.
Os itens são numerados (`F3.2`) para poder reportar "F3.2 falhou" sem
transcrever o passo.

Fonte: os testes manuais pendentes anotados nos rascunhos de PR da v1.0
(`.maestri/pr-pendente-feature-desktop-*.md`) e os seis achados de
`.maestri/levantamento-resiliencia-desktop.md`.

---

## 0. Preparo

### 0.1 Servidor

```bash
cd server
pip install -r requirements.txt
alembic upgrade head              # cria/atualiza o SQLite na primeira vez
uvicorn app.main:app --reload     # 127.0.0.1:8000
```

Variável recomendada para a regressão (arquivo `server/.env`):

```
SHOGUN_LLM_PROVIDER=deterministico
```

O provedor determinístico interpreta por palavra-chave, **sem credencial e sem
rede** — a mesma frase cai sempre na mesma ação, e o roteiro não gasta LLM pago
nem depende do Ollama estar carregado. Só os itens que testam 503 trocam de
provedor (F3.4).

`uvicorn --reload` escuta em `127.0.0.1`, então `SHOGUN_AUTH_TOKEN` é opcional
aqui; com bind aberto (`--host 0.0.0.0`) o servidor **recusa subir** sem token.

### 0.2 Desktop

```bash
cd desktop
npm ci
npm run tauri dev
```

`npm run build` (tsc + vite) valida tipos e empacota, mas **não exercita nada
em runtime** — para o roteiro, é `tauri dev` que vale.

Deixe o **console do WebView2 aberto** (clique direito → Inspecionar): toda
causa crua de falha é registrada lá com o prefixo `[shogun]`. Foi a ausência
desse registro que, no incidente de 05/09, transformou um erro de escopo do
plugin HTTP numa investigação com `netstat`.

### 0.3 Semear pendências (para o painel de Agentes)

Não existe rota de escrita de pendência; sem semear, o painel fica
legitimamente vazio. Rodando **de dentro de `server/`**, com o servidor
parado (SQLite):

```python
# semear.py — python semear.py, a partir de server/
from app.db import RepositorioPendencias
from app.db.engine import SessionLocal
from app.domain import ShogunOrquestradorProvider, StatusAgente

db = SessionLocal()
orq = ShogunOrquestradorProvider(repositorio=RepositorioPendencias(db))
orq.registrar_pendencia("agente-a", "Agente de Testes", "Aguardando revisao humana")
orq.registrar_pendencia(
    "agente-b", "Agente Travado", "Sem resposta do provedor", StatusAgente.TRAVADO
)
db.commit()
print([p.agente_nome for p in orq.get_pendencias_agentes()])
```

### 0.4 Servidor de mentira (só para F2.4, F3.5 e F3.6)

Três casos não dão para produzir com o servidor real: um 503 que **passa** na
segunda tentativa, resposta fora do formato e rota ausente (servidor antigo).
Este servidor de 30 linhas cobre os três — salve **fora do repositório** e
aponte a URL do desktop para `http://localhost:8010`:

```python
# servidor-de-mentira.py
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

comandos = 0


class Falso(BaseHTTPRequestHandler):
    def _json(self, codigo, corpo):
        bruto = json.dumps(corpo).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(bruto)))
        self.end_headers()
        self.wfile.write(bruto)

    def do_GET(self):
        if self.path == "/health":
            self._json(200, {"status": "ok"})
        else:
            self._json(404, {"detail": "rota inexistente"})     # F3.6

    def do_POST(self):
        global comandos
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        comandos += 1
        if comandos == 1:
            self._json(503, {"detail": "modelo frio"})          # F2.4, 1a tentativa
        else:
            self._json(200, {                                   # F2.4, 2a tentativa
                "session_id": "sessao-de-mentira",
                "text": "Resposta na segunda tentativa, Marcus.",
                "actions": [],
            })


HTTPServer(("127.0.0.1", 8010), Falso).serve_forever()
```

Para F3.5 (resposta fora do formato), trocar o corpo do `else` do `do_POST` por
uma escrita crua de `b"nao sou json"` com `Content-Length` compatível.

---

## F1 — `/health` e indicador de conexão

Achados 5 e 6 do levantamento: o app precisa dizer que não alcança o servidor
**antes** de gastar uma chamada de LLM, e a mesma queda não pode parecer dois
problemas.

| # | Passo | Esperado | Se falhar, olhar |
|---|---|---|---|
| F1.1 | Abrir o app com o servidor **de pé** | Splash roda; **nenhum** banner no topo (silencioso quando está tudo certo); campo de comando habilitado | `StatusServidor.tsx` (retorna `null` em `ok`), `checarSaude` em `App.tsx` |
| F1.2 | Fechar o servidor (Ctrl+C) e abrir o app | Banner "Servidor não alcançado." com o motivo "Não há servidor escutando em http://localhost:8000…"; campo de comando **desabilitado**, placeholder "Servidor não alcançado…" | `verificarSaude` e `traduzirFalhaDeRede` em `lib/api.ts`; console `[shogun] /health falhou` |
| F1.3 | Com o banner ativo, subir o servidor e clicar **"Verificar de novo"** | Banner passa por "Verificando o servidor…" e desaparece; campo volta a aceitar texto | `onVerificar` → `checarSaude`; `estadoServidor` em `App.tsx` |
| F1.4 | Apontar a URL para outro programa HTTP na mesma porta (ex.: `python -m http.server 8000`) | Banner com "…respondeu HTTP 404 em /health. Pode haver outro programa ocupando essa porta." | ramo `!resposta.ok` de `verificarSaude` (tipo `http`) |
| F1.5 | Apontar a URL para um host inexistente (`http://naoexiste.invalid:8000`) e salvar | Banner com "Não consegui resolver o endereço de…" | ramo `dns` de `traduzirFalhaDeRede` |
| F1.6 | Salvar nas Configurações uma URL nova (qualquer) | O `/health` é reconsultado **no salvar**, sem precisar mandar comando | `salvar()` em `App.tsx` (chama `checarSaude(nova)`) |

## F2 — Comando de texto ponta a ponta

| # | Passo | Esperado | Se falhar, olhar |
|---|---|---|---|
| F2.1 | Digitar "bom dia" e enviar | Bolha "Você"; samurai correndo com "Pensando…"; depois a bolha do Shogun com o selo 将 e a resposta do modo determinístico | `processarComando` em `App.tsx`; `POST /comando` no log do uvicorn |
| F2.2 | Digitar "quais são as pendências dos agentes" | A resposta lista as pendências semeadas em 0.3, ordenadas por prioridade | `_consultar_pendencias` em `server/app/api/comando.py`; `DeterministicoProvider._consultar_pendencias` |
| F2.3 | Enviar com o campo vazio ou só com espaços | Botão **Enviar** desabilitado; nada é enviado (nem sessão criada) | `enviar()` em `Chat.tsx`; guarda de 422 em `comando.py` |
| F2.4 | Contra o servidor de mentira (0.4): mandar um comando | **Uma** espera de ~2s e a resposta "Resposta na segunda tentativa, Marcus." aparece — o 503 foi reenviado automaticamente **uma vez** e passou. Dois `POST /comando` no log do servidor de mentira, nenhuma bolha de erro | `chamarComReenvio` e `ESPERA_REENVIO_MS` em `App.tsx` |
| F2.5 | Manter o app aberto com o painel de Agentes visível e conversar normalmente | O painel atualiza sozinho a cada 30s **sem** criar mensagem no chat e sem gastar LLM (o log mostra `GET /pendencias`, não `POST /comando`) | `REFRESH_AGENTES_MS` e o `useEffect` de refresh em `App.tsx` |

## F3 — Erros por tipo

O campo `tipo` de `ErroComando` é o que decide a reação: conexão vai para o
banner do topo, o resto fica onde ocorreu, e **só 503 reenvia sozinho**.

| # | Passo | Esperado | Se falhar, olhar |
|---|---|---|---|
| F3.1 | `rede` — matar o servidor **depois** de o app abrir e mandar um comando | Bolha de erro curta "Sem conexão com o servidor — veja o aviso no topo." + botão **"Tentar de novo"**; o detalhe da causa aparece **só no banner**, nunca duplicado | `registrarFalha` e `mensagemServidorFora` em `App.tsx`; `ehErroDeConexao` |
| F3.2 | Clicar **"Tentar de novo"** com o servidor de volta | A bolha de erro **desaparece**, a mensagem original do usuário permanece (nada duplicado) e a resposta chega | `tentarDeNovo` em `App.tsx`; `m.reenvio` em `Chat.tsx` |
| F3.3 | `auth` — subir o servidor com `SHOGUN_AUTH_TOKEN=segredo` e deixar o token vazio (ou errado) no app | Bolha no chat com "O servidor recusou o token (HTTP 401/403)…" ou "…exige autenticação e nenhum token está configurado"; **sem** banner de conexão e **sem** reenvio automático | ramo 401/403 em `enviarComando`; `core/security.py` |
| F3.4 | `llm_indisponivel` — subir com `SHOGUN_LLM_PROVIDER=claude` e **sem** `ANTHROPIC_API_KEY`, e mandar um comando | Uma pausa de ~2s (o único reenvio automático) e então a bolha "…provedor de LLM está indisponível no momento (503)…". Dois `POST /comando` no log | ramo 503 em `enviarComando`; `ClaudeProvider.interpretar_comando`; log "LLM indisponível" |
| F3.5 | `formato` — servidor de mentira devolvendo corpo não-JSON no `/comando` | Bolha "O servidor devolveu uma resposta fora do formato esperado."; console com `[shogun] resposta fora do formato` | `try/catch` do `resposta.json()` em `enviarComando` |
| F3.6 | `http`/404 — servidor de mentira (que só conhece `/health`): abrir a tela **Conversas** | Mensagem clara "O servidor não conhece /sessoes — atualize o servidor para carregar as conversas."; o app **não quebra** | ramo 404 de `getAutenticado` em `lib/api.ts` |
| F3.7 | `timeout` — subir um socket que aceita a conexão e nunca responde na 8011 (`python -c "import socket,time;s=socket.socket();s.bind(('127.0.0.1',8011));s.listen(5);time.sleep(600)"`) e apontar o app para `http://localhost:8011` | Após ~4s, banner "…aceitou a conexão mas não respondeu a tempo." — o `/health` tem limite próprio e **não** fica pendurado em "Verificando…" | `AbortController` de `verificarSaude`; `TIMEOUT_COMANDO_MS` (60s) e `TIMEOUT_LEITURA_MS` (8s) |
| F3.8 | Conferir que chat e painel não contam a mesma queda duas vezes: com o dividido ativo, matar o servidor e clicar Atualizar no painel | Banner único no topo com a causa; chat e painel exibem a **mesma** frase curta apontando para o topo | achado 6 do levantamento; `registrarFalha` (funil único) |

## F4 — 429 / rate limit

Rate limit é proteção de custo, não de segurança. Regra dura: **429 nunca
reenvia sozinho** — reenviar é exatamente o que o limite pune.

Preparo: subir o servidor com `SHOGUN_RATE_LIMIT_COMANDO_POR_MINUTO=1` e
`SHOGUN_RATE_LIMIT_LEITURA_POR_MINUTO=1`.

| # | Passo | Esperado | Se falhar, olhar |
|---|---|---|---|
| F4.1 | Mandar dois comandos seguidos | O segundo devolve a bolha "Muitas requisições em sequência — aguarde N segundos e tente de novo.", com **N vindo do `Retry-After`** | `erroDeRateLimit`/`segundosDeRetryAfter` em `lib/api.ts`; `core/rate_limit.py` |
| F4.2 | Conferir o log do servidor durante F4.1 | Apenas **um** `POST /comando` extra — nenhuma tentativa automática depois do 429 | `chamarComReenvio` (só trata `llm_indisponivel`) |
| F4.3 | Com o painel de Agentes aberto, esperar dois ticks | Depois do 429, o refresh **automático** fica suspenso pelo tempo do `Retry-After` (sem header, um ciclo de 30s) — o log não mostra `GET /pendencias` de 30 em 30s nesse intervalo | `pausaAgentesAteRef` em `App.tsx` |
| F4.4 | Durante a pausa de F4.3, clicar **Atualizar** no painel | O clique **não** é bloqueado (ação deliberada); se ainda estiver limitado, mostra a mensagem de 429, e um sucesso limpa a pausa | `atualizarAgentes` em `App.tsx` |
| F4.5 | Provocar um 503 (F3.4) cuja segunda tentativa tome 429 | Para ali, sem terceira tentativa; exibe a mensagem de 429 | ordem dos ramos em `enviarComando` + `chamarComReenvio` |

## F5 — Sessão persistida e nova conversa

| # | Passo | Esperado | Se falhar, olhar |
|---|---|---|---|
| F5.1 | Mandar dois comandos na mesma conversa | O segundo `POST /comando` leva o `session_id` que o primeiro devolveu (não nulo) | `atualizarSessao`; `salvarSessionId` em `lib/config.ts` |
| F5.2 | Fechar e reabrir o app; mandar um comando | O `session_id` **sobrevive ao fechamento** — a conversa continua a mesma (o histórico do banco entra como contexto) | `carregarSessionId`; `shogun.json` em `%APPDATA%` |
| F5.3 | Clicar **"Nova conversa"** na sidebar e mandar um comando | Chat limpa; o `POST` sai com `session_id: null`; o servidor abre sessão nova e o app adota o id novo. **Assunto antigo não vaza** | `novaConversa` em `App.tsx`; `_abrir_conversa` em `comando.py` |
| F5.4 | Conferir o `shogun.json` depois de "Nova conversa" | A chave `sessionId` é **removida**, não gravada como string vazia | `salvarSessionId(null)` em `lib/config.ts` |

## F6 — Histórico de conversas

| # | Passo | Esperado | Se falhar, olhar |
|---|---|---|---|
| F6.1 | Com duas ou três conversas criadas, abrir a tela **Conversas** | Lista carrega na entrada (sem clicar Atualizar), **mais recente no topo**, cada item com título (primeira mensagem do usuário), data/hora e contagem de mensagens | `useEffect` de `view === "conversas"`; `GET /sessoes` |
| F6.2 | Conferir a conversa em curso na lista | Marcada com o fio de tinta e o sufixo " · atual" — **sem bengara** (vermelho é só para erro) | classe `atual` em `Conversas.tsx` e `App.css` |
| F6.3 | Comparar a hora exibida com o relógio | Conversas de hoje aparecem em **hora local** (o banco grava UTC sem tzinfo e o app acrescenta o `Z` antes de converter) — nem 3h a mais, nem a menos | `quando()` em `Conversas.tsx`; `docs/DATABASE.md` |
| F6.4 | Abrir uma conversa antiga | O histórico completo aparece no chat, a tela volta para **Conversa**, e a **próxima mensagem continua naquela sessão** (conferir o `session_id` do `POST`) | `abrirConversa` em `App.tsx`; `GET /sessoes/{id}/mensagens` |
| F6.5 | Abrir uma conversa antiga enquanto a voz está falando | A fala em curso **cala** na hora (o áudio pertence ao contexto que estava na tela) | `calar()` no início de `abrirConversa` |
| F6.6 | Abrir a tela Conversas com o banco zerado | "Nenhuma conversa guardada ainda — a primeira mensagem cria uma." (vazio, não erro) | ramo `sessoes.length === 0` em `Conversas.tsx` |

## F7 — `abrir_app` (execução da `ClientInstruction`)

Único fluxo em que o cliente **executa** algo delegado pelo servidor. Nunca foi
testado em runtime (ressalva registrada no rascunho do PR): é o item de maior
risco do roteiro.

| # | Passo | Esperado | Se falhar, olhar |
|---|---|---|---|
| F7.1 | "abre a calculadora" | A **calculadora do Windows abre** e a bolha mostra o `text` do servidor ("Pedi para este aparelho abrir o calculadora, Marcus.") | `abrirApp`/`APPS_CURADOS` em `lib/instrucoes.ts`; `abrir-calculadora` em `src-tauri/capabilities/default.json` |
| F7.2 | "abre o navegador" | Navegador padrão abre no Google; bolha mostra o `text` | comando `abrir-navegador` (executável e args **fixos** no capabilities) |
| F7.3 | "abre o explorador de arquivos" | Explorer abre — sinônimo resolvido para `explorer` | `SINONIMOS` + `normalizar()` em `lib/instrucoes.ts` |
| F7.4 | "abre o Photoshop" (app fora do mapa curado) | **Nada** é executado; a bolha mostra o `fallback_text` ("Não consegui abrir o photoshop neste aparelho, Marcus.") e **nunca** os dois textos juntos; console com `[shogun] open_app: "…" fora do mapa curado.` | `executarInstrucoes` (regra de consumo do contrato) |
| F7.5 | Conferir no console que nenhuma string do servidor chega ao spawn | Só nomes de comando do mapa (`abrir-*`); executável e args vêm do capabilities, não do LLM | invariante de segurança em `lib/instrucoes.ts` |
| F7.6 | "abre o spotify" **sem** Spotify instalado | Aviso do próprio Windows (URI `spotify:` sem handler); o app **não** quebra e mostra o `text` — o spawn foi aceito | `abrir-spotify`; `spawn` em vez de `execute` (o explorer devolve exit code não-zero mesmo abrindo) |

## F8 — TTS (voz)

Nenhum agente tem alto-falante: **este bloco é 100% humano**.

Pré-requisito: conferir se há voz pt-BR instalada (Configurações do Windows →
Hora e idioma → Fala). Sem ela, a fala sai na voz default do sistema — é
fallback esperado, não bug.

| # | Passo | Esperado | Se falhar, olhar |
|---|---|---|---|
| F8.1 | Mandar "bom dia" com a voz ligada (padrão da v1.0) | A resposta é **falada**, em pt-BR, e o áudio bate palavra por palavra com a bolha | `falar()` em `lib/voz.ts`; chamada depois de `executarInstrucoes` em `App.tsx` |
| F8.2 | "abre a calculadora" | Fala o **texto de sucesso** (o mesmo `text` exibido) e abre o app | ordem instrução → exibir → falar em `processarComando` |
| F8.3 | "abre o Photoshop" | Fala o **`fallback_text`**, não o `text` — a regra do contrato vale para a voz | `executarInstrucoes` devolve um texto final único |
| F8.4 | Clicar no alto-falante da sidebar (ganha risco diagonal) e mandar outra mensagem | **Não fala**; o ícone mostra "Mudo", com `aria-pressed` | `alternarMudo` em `App.tsx`; `Sidebar.tsx` |
| F8.5 | Fechar e reabrir o app com o mudo ligado | Continua mudo — preferência persistida, como o tema | `mudo` em `lib/config.ts` |
| F8.6 | Mandar dois comandos em sequência rápida | A fala nova **cancela** a anterior; nada de duas vozes sobrepostas | `sintese.cancel()` antes do `speak()` em `lib/voz.ts` |
| F8.7 | Mutar (ou clicar "Nova conversa") **durante** uma fala longa | A fala para na hora | `calar()` em `alternarMudo`, `novaConversa`, `abrirConversa` e `salvar` |
| F8.8 | Provocar um erro (F3.1) e ouvir | Erros, banner e painel de Agentes **não falam** — voz só nas respostas do chat | `falar()` só no caminho de sucesso de `processarComando` |
| F8.9 | Radiogroup Falar/Mudo nas Configurações | Reflete e altera o mesmo estado do ícone da sidebar — uma preferência, dois controles | `Configuracoes.tsx` |

## F9 — Painel de Agentes

| # | Passo | Esperado | Se falhar, olhar |
|---|---|---|---|
| F9.1 | Abrir o app com pendências semeadas (0.3) | Painel povoa **sem clique** (tick inicial); rodapé com total e "atualizado às HH:MM:SS" | tick inicial do `useEffect` de refresh em `App.tsx` |
| F9.2 | Conferir a pendência de status `travado` | Ganha o **bengara**; `pendente`/`executando` ficam neutras | `STATUS_CRITICOS` em `PainelAgentes.tsx` |
| F9.3 | Ativar o modo **dividido** na sidebar | Chat e Agentes lado a lado; Conversas e Configurações ficam fora do dividido | `dividido` em `App.tsx`; `Sidebar.tsx` |
| F9.4 | Matar o servidor e esperar dois ticks | O refresh automático **para** enquanto o banner está ativo e **volta sozinho** quando o `/health` passa, sem clique | guarda `estadoServidor !== "ok"` no `useEffect` |
| F9.5 | Clicar **Atualizar** repetidamente durante uma consulta em curso | Botão desabilitado ("Consultando…"); nenhuma consulta sobreposta | `consultandoAgentesRef` em `App.tsx` |
| F9.6 | Banco sem pendências | "Nenhuma pendência aberta."; durante a primeira consulta, "Consultando as pendências…" | ramos de `atualizadoEm` em `PainelAgentes.tsx` |

---

## Cobertura: automático × humano

### O que passou automático (em `origin/dev` @ `9a3b433`, 10/09/2026)

| Comando | Onde | Resultado |
|---|---|---|
| `npm ci` | `desktop/` | ok |
| `npm run build` (`tsc && vite build`) | `desktop/` | **ok** — tipos limpos, bundle gerado. Não existe script de teste no `package.json` |
| `cargo test` | `desktop/src-tauri/` | **ok, 0 testes** — compila lib, bin e doc-tests; nenhum teste existe do lado Rust. Vale como `cargo check` do `capabilities/default.json` |
| `pytest` | `server/` | **231 passaram** em 6,45s |

O que isso garante: o TypeScript é coerente, o bundle sai, o Rust compila com o
escopo de permissões que o `abrir_app` exige, e o servidor inteiro (rotas, rate
limit, sessões, pendências, LLM mockado, migrações) está verde.

### O que exige olho humano

Nada do cliente desktop é coberto por teste automatizado — abaixo, o que **só**
o roteiro acima verifica:

- **Áudio (F8 inteiro).** Nenhum agente tem alto-falante. Fala, voz pt-BR,
  cancelamento e mudo persistido são exclusivamente humanos.
- **`abrir_app` em runtime (F7).** Nunca foi executado de verdade — o
  `cargo test`/`check` valida o *capabilities*, mas app abrindo é runtime.
  Maior risco do roteiro.
- **Toda a UI de erro (F1, F3, F4).** Roteamento banner × bolha, botão "Tentar
  de novo", classificação por tipo, o único reenvio de 503 e a suspensão do
  polling em 429 vivem em `App.tsx`/`api.ts`, sem teste.
- **Persistência local (F5, F8.5).** O `tauri-plugin-store` só existe no app
  em execução; `%APPDATA%\shogun.json` não é verificável fora dele.
- **Fuso horário e formatação de data (F6.3).** O sufixo `Z` acrescentado no
  cliente só se confirma comparando com o relógio.
- **Splash, wordmark animado e `prefers-reduced-motion`.** Fora do roteiro por
  não serem regressão funcional; conferir de olho ao abrir.

**Lacuna conhecida:** o desktop não tem *nenhum* teste de unidade. Se a v1.1
quiser fechar essa lacuna, os candidatos mais baratos são funções puras já
isoladas: `normalizar`/`executarInstrucoes` (`lib/instrucoes.ts`),
`segundosDeRetryAfter`/`traduzirFalhaDeRede` (`lib/api.ts`) e `quando()`
(`Conversas.tsx`).
