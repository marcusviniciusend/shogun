# Roadmap — Shogun

> **Documento vivo.** Atualize conforme decisões forem tomadas ou novas ideias
> surgirem. Quando divergir do código, o código vence — e este arquivo precisa
> ser corrigido.
>
> Última atualização: 2026-09-07.

---

## Fase atual (v1.0 — desktop)

O foco é levar o **cliente desktop** a uma versão 1.0. O servidor já sustenta
isso; o que falta é sobretudo do lado do cliente.

### O que já existe

**Servidor multi-provider de LLM**
`POST /comando` com autenticação Bearer, `422` para comando vazio e `503` quando
o modelo cai. A interpretação fica atrás do `Protocol` `LLMProvider`, com cinco
implementações — `claude`, `deepseek`, `openai_mini`, `ollama` (local) e
`deterministico` (palavras-chave, sem chave de API, nunca indisponível) — e
`FallbackLLMProvider` para quando o principal falha. `SYSTEM_PROMPT` e
`ESQUEMA_COMANDO` são compartilhados por todos: trocar de modelo não muda quem o
Shogun é. Escolher provedor e fallback é só variável de ambiente.

Ações despachadas hoje: `conversar` (resposta livre), `consultar_pendencias`
(via `PendenciasProvider` injetado, persistente no banco) e `abrir_app` —
delegada ao cliente via `ClientInstruction` (`shared/`): o servidor manda só o
nome do app, o cliente executa a partir de um mapa curado e cai no
`fallback_text` quando não suporta.

**Rotas de leitura e proteção de custo**
Além do `POST /comando`: `GET /pendencias` (painel sem gastar LLM),
`GET /sessoes` + `GET /sessoes/{id}/mensagens` (histórico de conversas) e
`GET /consumo` (tokens e custo por provedor). Rate limit por token com janela
deslizante de 60 s — dois baldes (comando 20/min, leitura 120/min), estouro
vira 429 com `Retry-After`. No startup, o servidor recusa subir com migração
Alembic pendente e aquece o modelo local em segundo plano, eliminando o 503 do
primeiro comando do dia.

**Persistência e memória de conversa**
SQLite via SQLAlchemy, com `sessions` e `messages` e migração Alembic. O
`session_id` é opcional no request: nulo cria a sessão e o servidor devolve o id,
que o cliente guarda e reenvia. Antes de chamar o modelo, a rota lê as últimas
`SHOGUN_HISTORICO_MAX_MENSAGENS` (default 20) e as concatena ao prompt — a
interface `LLMProvider` continua recebendo uma string só.

**Acesso remoto via Tailscale**
`SHOGUN_HOST`/`SHOGUN_PORT` respeitados por `python -m app.main`. O servidor
**recusa subir** quando o bind aceita conexões de outras máquinas e
`SHOGUN_AUTH_TOKEN` está vazio — e a checagem lê o host que o uvicorn realmente
recebeu, não a variável de ambiente. CORS só entra quando
`SHOGUN_ALLOWED_ORIGINS` tem valor.

**App desktop**
Tauri 2 + React (TypeScript), com chat, painel de agentes e configurações. O
`session_id` é persistido via `tauri-plugin-store`; há botão "Nova conversa" e
lista de conversas antigas via `GET /sessoes`. O painel de agentes consome o
`GET /pendencias` com refresh automático (polling de 30 s), sem gastar chamada
de LLM. O desktop **executa** o `abrir_app` delegado (mapa curado de apps, com
o escopo do `tauri-plugin-shell` travando executável e args) e **fala as
respostas** — TTS via `speechSynthesis` do WebView2, voz pt-BR quando
disponível, com opção de mudo nas configurações. Os tipos de `POST /comando`
vêm de `shared/ts`; os dos GETs de leitura ainda são cópia local em
`types.ts` (a promoção para `shared/` já aconteceu do lado do servidor — a
migração do desktop é follow-up registrado).

**Resiliência no desktop**
O erro de rede deixou de ser engolido: a exceção vai para o console e a mensagem
distingue "ninguém escutando na porta", "aceitou a conexão mas não respondeu" e
"nome que não resolve", com fallback que preserva o texto original. O app
checa `GET /health` — ~1,5 ms, sem token, sem tocar no modelo — ao abrir, ao
salvar configurações e antes de cada envio, com faixa visível quando o servidor
não responde. O `POST /comando` tem timeout de 60 s; 503 (modelo indisponível)
tem reenvio automático — modelo frio costuma responder na segunda tentativa — e
falha de conexão vira bolha de erro com botão "Tentar de novo", sem reenviar
sozinho.

**Infraestrutura**
CI no GitHub Actions a cada push e PR para `dev` e `main`, em Python 3.11 e 3.13.
Suíte do servidor: 231 testes na última execução, nenhum chamando API real. A
paridade entre `shared/python` e `shared/ts` é verificada por teste (parse
estático do TS, sem toolchain Node no CI).

### O que ainda falta para chamar de v1.0

Levantado pelo coordenador, **não é decisão fechada** — vale revisar o corte:

1. **Streaming** (passos 6 e 7 do [DESIGN.md](DESIGN.md)) — único item de código
   em aberto. Aguardando o documento de design do backend (a tensão contra a
   saída estruturada dos provedores precisa ser resolvida antes de implementar).
2. **STT** — decidido ficar **fora da v1.0**: entra na v1.1. A metade TTS já
   existe (o desktop fala as respostas); a v1.0 fecha com entrada por texto.

Concluídos desde o levantamento original: ~~contrato e execução de
`abrir_app`~~ (PRs #24/#26), ~~primeiro comando do dia falhando com modelo
frio~~ (aquecimento no startup + reenvio automático no 503, PRs #23/#22),
~~resiliência restante do desktop — timeout, retry, erro em duplicata~~
(PR #22) e ~~TTS~~ (PR #31).

---

## Backlog — Mobile

**Retomar após o desktop atingir v1.0.**

O app já tem scaffold funcional em React Native + Expo, com chat, status e
config, mergeado em `dev` e passando em `tsc --noEmit`. Ele fica parado onde
está.

O plano detalhado de integração com o servidor — token seguro, sessão,
offline, `AgentAction` — já está escrito e **aprovado** (PR #17):
[plano-integracao-mobile.md](plano-integracao-mobile.md). Quando o
congelamento for levantado, a ordem de implementação proposta lá é o ponto
de partida.

O que falta antes de considerá-lo pronto:

- **Paridade de resiliência com o desktop.** O ponto de partida não é zero: o
  mobile já tem timeout de 60 s com `AbortController` (o desktop o ganhou depois,
  no PR #22, junto com retry). Falta registrar a causa crua do erro e separar as
  falhas de rede (hoje agrupadas numa frase só), e tornar a checagem de `/health`
  automática — ela existe, mas só no botão "testar conexão" da aba Config, então
  o chat continua descobrindo que o servidor caiu gastando uma chamada de LLM.
  Falta também indicador visível de servidor inalcançável nas telas de uso.
- **Testes reais em aparelho.** Nada além de type-check foi exercitado. A skill
  `react-native-best-practices` (Callstack) está instalada para essa fase.

Detalhes na seção 1.3 de [CONTEXTO-GERAL.md](CONTEXTO-GERAL.md) e no
`mobile/README.md`.

---

## Ideias futuras (sem prazo definido)

### Visão computacional

Três frentes possíveis, **nenhuma iniciada**:

1. **Analisar imagens enviadas pelo usuário** — fotos, documentos, prints — via
   modelo multimodal. É a de menor complexidade: pode usar Claude ou
   GPT-4o-mini, que já suportam visão, ou um modelo local multimodal (LLaVA,
   Llama 3.2 Vision) via Ollama, já que os candidatos 8B atuais de texto não
   processam imagem.
2. **Ler a tela do PC** (screenshots) para entender o contexto do que o usuário
   está fazendo. Depende de captura de tela via Tauri, do mesmo modelo com
   visão, e da decisão de quando e como capturar.
3. **Reconhecimento facial / presença** — detectar quando o usuário está na
   frente do PC, para ativação automática. A de maior complexidade: câmera,
   modelo de detecção rodando em background, e considerações de privacidade e
   performance.

**Prioridade sugerida:** imagens enviadas primeiro — é a mais simples e encaixa
no fluxo `/comando` existente como um novo tipo de entrada; depois leitura de
tela; por último presença/facial.

Uma observação de arquitetura, para quando a primeira frente for atacada: a
interface `LLMProvider` hoje é `interpretar_comando(texto: str)`. Aceitar imagem
muda essa assinatura, o que atinge os cinco provedores de uma vez — e o
`hermes3:8b` local ficaria de fora, tornando o fallback de nuvem obrigatório
para comandos com imagem. É a mesma discussão de assinatura registrada no passo
4 do [DESIGN.md](DESIGN.md), e vale resolver as duas juntas.

### Outras ideias registradas

*(espaço reservado — acrescente aqui conforme surgirem)*

- ~~**Endpoint direto de pendências**, sem passar pelo LLM~~ → resolvido:
  `GET /pendencias` (PR #25), e o painel do desktop consome com refresh
  automático (PR #30).
- ~~**Provedor de LLM determinístico** (interpretação por palavras-chave),
  registrado em `PROVIDERS`~~ → resolvido: `DeterministicoProvider` mergeado em
  `dev` (PR #19), em `core/llm/deterministico.py`, coberto por testes.
- **Geração dos contratos a partir de schema.** `shared/contracts/` está vazia; o
  plano era derivar `ts/` e `python/` de JSON Schema. O risco de dessincronia
  ficou bem menor — `server/tests/test_paridade_contratos.py` compara as duas
  pontas por parse estático e falha no CI quando divergem — mas a geração
  eliminaria a classe de erro por construção.
- ~~**Animação do wordmark 将軍** fora do repositório~~ → resolvido: o projeto
  Remotion está em `anim/`, com uma composição por tema do app.

---

## Marcos

| Fase | Estado |
|---|---|
| Servidor central | ✅ funcional |
| Persistência e memória de conversa | ✅ funcional |
| Acesso remoto (Tailscale) | ✅ funcional |
| Desktop v1.0 | 🟡 em andamento — resta streaming (e a decisão de ele entrar no corte) |
| Voz (STT/TTS) | 🟡 parcial — TTS funciona no desktop (`speechSynthesis`); STT fica para a v1.1 |
| Mobile | ⏸️ backlog |
| Visão computacional | 💡 ideia |
