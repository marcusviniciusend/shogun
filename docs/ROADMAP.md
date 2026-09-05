# Roadmap — Shogun

> **Documento vivo.** Atualize conforme decisões forem tomadas ou novas ideias
> surgirem. Quando divergir do código, o código vence — e este arquivo precisa
> ser corrigido.
>
> Última atualização: 2026-09-05.

---

## Fase atual (v1.0 — desktop)

O foco é levar o **cliente desktop** a uma versão 1.0. O servidor já sustenta
isso; o que falta é sobretudo do lado do cliente.

### O que já existe

**Servidor multi-provider de LLM**
`POST /comando` com autenticação Bearer, `422` para comando vazio e `503` quando
o modelo cai. A interpretação fica atrás do `Protocol` `LLMProvider`, com quatro
implementações — `claude`, `deepseek`, `openai_mini` e `ollama` (local) — e
`FallbackLLMProvider` para quando o principal falha. `SYSTEM_PROMPT` e
`ESQUEMA_COMANDO` são compartilhados por todos: trocar de modelo não muda quem o
Shogun é. Escolher provedor e fallback é só variável de ambiente.

Ações despachadas hoje: `conversar` (resposta livre), `consultar_pendencias`
(via `PendenciasProvider` injetado) e `abrir_app` — esta última ainda um
placeholder, à espera do contrato servidor→cliente.

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
`session_id` é persistido via `tauri-plugin-store`, então a conversa sobrevive a
reaberturas. Os tipos do fio vêm de `shared/ts`, sem cópia local.

**Resiliência básica no desktop**
O erro de rede deixou de ser engolido: a exceção vai para o console e a mensagem
distingue "ninguém escutando na porta", "aceitou a conexão mas não respondeu" e
"nome que não resolve", com fallback que preserva o texto original. E o app
checa `GET /health` — ~1,5 ms, sem token, sem tocar no modelo — ao abrir, ao
salvar configurações e antes de cada envio, com faixa visível quando o servidor
não responde.

**Infraestrutura**
CI no GitHub Actions a cada push e PR para `dev` e `main`, em Python 3.11 e 3.13.
Suíte do servidor: 134 testes na última execução, nenhum chamando API real.

### O que ainda falta para chamar de v1.0

Levantado pelo coordenador, **não é decisão fechada** — vale revisar o corte:

1. **Voz.** Nem STT nem TTS existem em lugar nenhum. Hoje a conversa é por
   texto, o que é uma distância considerável de "assistente pessoal de voz".
   É o maior item em aberto.
2. **`abrir_app`.** Falta o contrato servidor→cliente: o servidor devolve a
   `AgentAction`, o cliente executa no sistema operacional.
3. **Primeiro comando do dia falha.** O modelo local leva mais de 30 s para
   carregar frio e o `SHOGUN_LLM_TIMEOUT` é 30 s. Sem retry, o padrão que se
   aprende é "falha e depois funciona". Ver item 4 do
   `.maestri/levantamento-resiliencia-desktop.md`.
4. **Resiliência restante do desktop** — timeout de resposta no `POST /comando`,
   retry e erro em duplicata entre chat e painel (itens 2, 3 e 6 do mesmo
   levantamento).
5. **Streaming** (passos 6 e 7 do [DESIGN.md](DESIGN.md)), com a tensão de
   desenho contra saída estruturada ainda por resolver.

---

## Backlog — Mobile

**Retomar após o desktop atingir v1.0.**

O app já tem scaffold funcional em React Native + Expo, com chat, status e
config, mergeado em `dev` e passando em `tsc --noEmit`. Ele fica parado onde
está.

O que falta antes de considerá-lo pronto:

- **Paridade de resiliência com o desktop.** O ponto de partida não é zero, e num
  aspecto o mobile está à frente: já tem timeout de 60 s com `AbortController`,
  que o desktop ainda não tem. Falta registrar a causa crua do erro e separar as
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
   Llama 3.2 Vision) via Ollama, já que o `hermes3:8b` atual não processa imagem.
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
muda essa assinatura, o que atinge os quatro provedores de uma vez — e o
`hermes3:8b` local ficaria de fora, tornando o fallback de nuvem obrigatório
para comandos com imagem. É a mesma discussão de assinatura registrada no passo
4 do [DESIGN.md](DESIGN.md), e vale resolver as duas juntas.

### Outras ideias registradas

*(espaço reservado — acrescente aqui conforme surgirem)*

- **Endpoint direto de pendências**, sem passar pelo LLM. Hoje o painel de
  agentes do desktop gasta uma chamada de modelo para saber o status, e é por
  isso que o refresh é manual. Com um endpoint próprio, dá para automatizar.
- **Provedor de LLM determinístico** (interpretação por palavras-chave),
  registrado em `PROVIDERS`. Destravaria o fluxo ponta a ponta sem nenhuma chave
  de API, e serviria de base para testes de integração.
- **Geração dos contratos a partir de schema.** `shared/contracts/` está vazia; o
  plano era derivar `ts/` e `python/` de JSON Schema. Sem isso, os dois lados
  saem de sincronia — já aconteceu uma vez (`sessionId` × `session_id`).
- **Animação do wordmark 将軍.** Existe uma composição Remotion pronta e
  renderizada, com os traços do KanjiVG desenhados e desescritos em ordem
  caligráfica, mas ela vive num diretório temporário e não está versionada.

---

## Marcos

| Fase | Estado |
|---|---|
| Servidor central | ✅ funcional |
| Persistência e memória de conversa | ✅ funcional |
| Acesso remoto (Tailscale) | ✅ funcional |
| Desktop v1.0 | 🟡 em andamento |
| Voz (STT/TTS) | 🔴 não iniciado |
| Mobile | ⏸️ backlog |
| Visão computacional | 💡 ideia |
