# L1 — Decisões

Append **no topo**, com data absoluta. Uma decisão entra aqui quando sobrevive
à tarefa que a gerou. O formato é sempre: **o quê**, **por quê**, **o que isso
proíbe daqui pra frente**.

---

## 2026-09-19 — Semântica das ações: fonte única, dois canais derivados

**O quê:** o significado de cada valor de `Acao` passa a viver numa constante
só — `SEMANTICA_ACOES` em `core/llm/base.py`. O `ESQUEMA_COMANDO` (json_schema
de claude/openai_mini) e a `DICA_ESQUEMA` (único canal em linguagem natural de
deepseek/ollama) são os dois derivados dela. O `SYSTEM_PROMPT` não foi tocado.

**Por quê:** a `description` do `ESQUEMA_COMANDO` não chega em todos os
provedores — deepseek não recebe schema nenhum e o ollama recebe o schema como
gramática, que garante forma e não semântica (`ollama.py`). Corrigir só ali
alcançaria 2 dos 4 provedores, e nenhum deles é o provedor onde o bug de
classificação foi reproduzido. Escrever o texto duas vezes resolveria o alcance
e criaria divergência silenciosa; derivar resolve os dois.

O `SYSTEM_PROMPT` ficou de fora porque ele é identidade ("trocar de LLM não pode
mudar quem o Shogun é", `CLAUDE.md` §2), e o significado de um valor do enum de
saída é formato, não identidade.

**Proíbe:** reescrever a semântica de uma ação direto no `ESQUEMA_COMANDO` ou na
`DICA_ESQUEMA` — os dois são derivados, a edição é em `SEMANTICA_ACOES`. Proíbe
também gerar a lista de estados do prompt a partir de `StatusAgente`: o teste
`test_semantica_acoes.py` deriva daquele enum, e gerar o prompt dele tornaria a
guarda tautológica.

---

## 2026-09-18 — Agentes organizados por fase, não por domínio

**O quê:** o canvas Maestri deixou de ter um agente por área (backend,
contratos, desktop, mobile) e passou a ter um por fase do trabalho:
Scout → Architect → Coder → Tester → Reviewer, com o coordenador no topo.
Contexto entra por nível (L0/L1/L2) em vez de cada agente reler o repositório.

**Por quê:** o split por domínio fazia cada agente recarregar o mesmo contexto
de projeto toda rodada, e ninguém tinha o papel de revisar. O split por fase dá
handoff estruturado (cada agente entrega o que o próximo precisa) e põe uma
revisão antes do humano.

**Proíbe:** agente pedir contexto que seu nível não inclui — se o Tester precisa
do desenho, o handoff do Architect estava incompleto; conserte o handoff, não o
nível.

---

## 2026-09-15 — Ditado por clique-alterna, não push-to-talk

**O quê:** o botão de microfone do desktop alterna por clique (estilo WhatsApp),
com cronômetro e medidor de nível. Registrado em `docs/stt-desktop-design.md`
§5.1 e refletido em `docs/roteiro-ditado.md`.

**Por quê:** ditado longo cansa a mão; segurar prende o ponteiro numa janela que
o usuário pode querer usar enquanto fala; e o teclado sai de graça — um
`<button>` com `onClick` já responde a espaço e enter. Sumiram os
`keydown`/`keyup` com guarda de `e.repeat` e o `setPointerCapture`: seis
handlers viraram um.

**Proíbe:** reintroduzir gesto de segurar sem reabrir a decisão.

---

## 2026-09-15 — Nível do microfone vem por poll, não por evento

**O quê:** o `Acumulador` guarda o maior absoluto desde a última leitura
(`pico_parcial`); o comando `microfone_nivel` devolve pico + duração; a UI
pergunta a cada 70 ms. **Ler zera a janela do pico.**

**Por quê:** o callback de áudio do `cpal`
(`desktop/src-tauri/src/microfone.rs`) não pode alocar nem fazer I/O — emitir
evento Tauri de dentro dele faria as duas coisas.

**Proíbe:** emitir evento de dentro do callback de áudio. E não remova o zeramento
na leitura: sem ele o medidor vira catraca.

**Nota:** o cronômetro conta **amostras**, não relógio de parede — é o tempo do
áudio que será de fato transcrito. Thread de áudio travada congela o número, e
esse número congelado é a verdade.

---

## 2026-09-15 — O portal Maestri não exercita o cliente desktop

**O quê:** abrir `http://localhost:1420` num portal renderiza a casca e nada
funciona. O portal serve **só para QA visual** (layout, CSS, responsividade).

**Por quê:** dois bloqueios arquiteturais, os dois de propósito —
`desktop/src/lib/api.ts` importa `fetch` de `@tauri-apps/plugin-http` (toda
chamada passa pelo Rust, para não depender de origem de navegador), e
`sttDisponivel()` devolve `isTauri()`, false no navegador.

**Proíbe:** propor automatizar passo de roteiro de regressão pelo portal. Já foi
proposto uma vez e estava errado. Não adianta liberar CORS — esse diagnóstico
foi tentado e revertido.

---

## 2026-09-10 — Branch default do GitHub é `dev`

**O quê:** a default do repositório passou a ser `dev`. Todo PR já nasce
apontando para `dev`.

**Proíbe:** a conferência manual de base, que virou ruído. `main` continua sendo
promovida só por PR de marco.

---

## 2026-09-08 — Streaming fora da v1.0

**O quê:** streaming não entrou na v1.0; desenho escolhido para depois é o
streaming do campo final. Registrado em `docs/streaming-design.md` (#35).
