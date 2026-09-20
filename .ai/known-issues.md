# L1 — Problemas conhecidos

Bug achado e **não corrigido** entra aqui, com o motivo de não ter sido
corrigido. Append no topo, data absoluta. Ao corrigir, mova para "Resolvidos"
com o commit/PR.

---

## Abertos

### Classificação: agenda pessoal cai em `consultar_pendencias` (qwen)
`server/app/core/llm/base.py` · achado em 2026-09-19 pelo Kama, na validação da
branch `feature/prompt-classificacao-pendencias`

Vizinho do bug de horário corrigido nesta rodada (ver "Resolvidos"), e **não
corrigido por ela**. Com `qwen2.5:7b-instruct` — o modelo em produção —
"tenho algum compromisso marcado hoje a tarde" e "Tenho algum compromisso
amanhã?" caem em `consultar_pendencias` **0/5 antes e 0/5 depois**: 10 chamadas,
10 erradas, o ponteiro não se mexeu.

O incômodo é que `SEMANTICA_ACOES` trata este caso explicitamente nas duas
pontas — `conversar` reivindica "agenda pessoal", `consultar_pendencias` nega
"agenda, compromisso". O qwen ignora as duas. O `hermes3:8b` obedece: 0/5 antes,
5/5 depois.

**Não corrigido de propósito:** a correção é mudança de prompt, ou seja, código
de produção, e só o Coder escreve código de produção (`CLAUDE.md` §5). Não entra
de carona numa branch já empurrada e fechada em torno do bug de horário.
Medição completa em `.maestri/relatorio-teste-rodada-1.md` §4.3 — artefato
local, `.maestri/` é gitignored.

**Para quem for atacar:** a guarda de regressão já existe
(`test_semantica_acoes.py`), então mexer na redação é barato. O que não existe é
prova de que uma redação nova resolve — isso só se mede com ollama local, fora
do CI, e **com as frases ao pé da letra**: acento e pontuação mudam o resultado.

**Atualização de 2026-09-19 (rodada 2):** a rodada 2 mexeu em
`SEMANTICA_ACOES["conversar"]`, mas **não para atacar este item** — o alvo dela
foi o ramo `conversar` mentir, não o roteamento. A classificação de agenda pode
continuar exatamente como está e a rodada 2 ainda assim ter cumprido o que
prometeu; ver a decisão de 2026-09-19 em [`decisions.md`](decisions.md) e o
critério do Architect em `.maestri/plano-rodada-2.md` §7.3. **Se continuar
0/5**, a saída registrada é esta: a resposta de `consultar_pendencias` é
"Nenhuma pendência registrada, Marcus" — verdade, e fora do assunto. O que
**não** deve ser feito é mais uma rodada de texto empurrando na mesma direção,
que é exatamente o que já não moveu o ponteiro.

### `conversar` inventa hora de outro fuso
`server/app/core/llm/contexto.py` · achado em 2026-09-19 pelo Kama, rodada 2

O bloco de contexto entrega "hora local do servidor" sem dizer **qual** fuso.
Perguntado a hora em cidade de outro fuso, o `qwen2.5:7b-instruct` afirma uma
conversão que não fez: "Em Lisboa, as horas são 22:29" (correto: 03:29), 5/5,
com a justificativa "considerando a diferença horária". Manaus: 1/5 fabrica,
4/5 admite.

Não pegou na rodada 2 porque a frase medida (São Luís) é UTC−3, o mesmo fuso
do servidor — acerta por coincidência. **Não corrigido:** é prompt, ou seja,
código de produção. As saídas plausíveis são nomear o fuso no bloco ou
instruir a não converter; qual delas é desenho, não implementação.

**Nota do Kaji, sobre reusar o critério:** o §7.2 do
`.maestri/plano-rodada-2.md` define ANCORADA como "confere com o instante
injetado", o que premia repetir o relógio do servidor como se fosse a hora de
outra cidade. Em São Luís isso é indistinguível de acertar. Quem for reusar o
critério precisa fechar esse buraco antes de medir fuso.

### `conversar` inventa dado que o servidor não tem
`server/app/api/comando.py` · achado em 2026-09-19 na rodada 2 · **mitigado, não
fechado**, na branch `feature/prompt-classificacao-pendencias`

`consultar_pendencias` e `abrir_app` constroem a fala a partir de dado do
servidor e descartam a `resposta_falada` do modelo. `conversar` fala o texto do
modelo **verbatim**. É o único ramo da rota por onde uma alucinação chega ao
Marcus, e a assimetria não estava escrita em lugar nenhum antes desta rodada.

Medido com modelo real: perguntado sobre agenda, o modelo inventou reunião,
horário e nome próprio — 3/3, idêntico, sem hedge. Perguntado a hora, respondeu
"14:30" às 19:47.

**O que a rodada 2 fez:** injetou data e hora reais no prompt
(`core/llm/contexto.py`), separou roteamento de capacidade em `conversar` e
acrescentou a `REGRA_DE_HONESTIDADE` nos dois canais de prompt.

**Por que continua aberto:** nada disso prova que o modelo obedece. A suíte
garante que o dado é montado e que o texto alcança os quatro provedores — **um
teste de CI não vê fabricação**, e um que visse deixaria de ser unitário
(`CLAUDE.md` §3). Só medição local com ollama fecha ou mantém este item, e o
critério está em `.maestri/plano-rodada-2.md` §7.2 (ANCORADA / ADMISSÃO /
FABRICAÇÃO, na dúvida conte como fabricação).

**Se o 7B ignorar a regra de honestidade também:** aí há evidência forte para
"é limite do modelo" — mas sobre *fabricação*, que é muito mais sério que
"agenda cai em pendências" e provavelmente muda a conversa sobre qual modelo
fica em produção. Reportar, não improvisar redação nova.

### F10.10 — "Nova conversa" não interrompe a gravação
`desktop/src/App.tsx` · achado em 2026-09-15

`novaConversa()` não desmonta o `<Chat>`, então o `useEffect` de limpeza
(`Chat.tsx`, `controle.cancelar()`) nunca roda e a gravação sobrevive ao "Nova
conversa". A metade "trocar de tela" do item funciona; só a metade "Nova
conversa" quebrou.

**Não corrigido de propósito:** não misturar escopo com a branch do ditado por
clique.

### F10.15 — Etiquetas do whisper viram comando
`desktop/src/lib/ditado.ts` · achado em 2026-09-15

`textoUtil` filtra só string vazia. O whisper devolve `[Musica]` /
`[BLANK_AUDIO]` em áudio sem fala, e essas etiquetas passam e viram comando.

**Não corrigido de propósito:** mesmo motivo do F10.10.

### Orquestrador persistente pronto e vazio
`server/` · #27/#29

Nada chama `registrar_pendencia`. Falta desenhar quem produz pendência (rotina
interna? webhook? placeholder do Maestri?).

---

## Resolvidos

### `str(exc)` vaza ao cliente
`server/` · rotas de erro · resolvido em 2026-09-10 pelo PR #37 (merge `47a40dd`)

Detalhe de exceção chegava na resposta ao cliente; passou a ser mensagem
genérica ao cliente e detalhe só no log. `grep -rn "str(exc)" server/app/api/`
não retorna nada.

O item ficou listado como aberto por engano: já estava defasado desde 10/09 e
foi copiado para o `.ai/` em 18/09, na criação da camada, sem conferência no
código. A rodada 8 de `.maestri/proximas-rodadas.md` ainda o cita — quem for
executá-la não precisa dele.

### Classificação: horário cai em `consultar_pendencias`
`server/app/core/llm/base.py` · achado em 2026-09-15 · corrigido em 2026-09-19
na branch `feature/prompt-classificacao-pendencias` (PR ainda não aberta)

A descrição de `consultar_pendencias` dizia só "o Marcus quer saber o que está
pendente" — sem dizer que pendência ali é **status de agente**. Modelos pequenos
associavam horário/agenda a "coisas pendentes".

A correção não foi só reescrever a descrição. O `ESQUEMA_COMANDO` não chega em
todos os provedores, então o significado das ações virou fonte única
(`SEMANTICA_ACOES`) com os dois canais de prompt derivados dela — ver
[`decisions.md`](decisions.md), entrada de 2026-09-19. `conversar` passou a
reivindicar horário/data/clima/agenda de propósito: negar num lugar sem dar
destino no outro deixaria a pergunta órfã.

**Verificado em 2026-09-19** pelo Kama, com ollama local (fora do CI: a suíte
garante que o vocabulário do domínio não desaparece do prompt, não que um 7B
obedeça). 212 chamadas, `origin/dev` contra `HEAD`, mesmo modelo e mesmo
provedor dos dois lados:

| Modelo | Frase | Antes | Depois |
|---|---|---|---|
| `qwen2.5:7b-instruct` | "Qual o horário agora?" | 0/5 | **5/5** |
| `qwen2.5:7b-instruct` | "Que horas são em São Luís Maranhão" | 0/5 | **5/5** |
| `hermes3:8b` | as duas acima | 5/5 | 5/5 |

Duas correções ao enunciado original, que dizia "3/3 com `qwen2.5:7b` **e** com
`hermes3:8b`":

1. **O hermes nunca reproduziu essas frases** — acertava 5/5 antes da correção.
   O que ele errava era o caminho oposto: "Quais agentes estão travados?" caía
   em `conversar` 0/5, e a correção levou a 5/5. O ganho é real, só é outro.
2. **A formulação importa mais do que parecia.** "que horas sao agora", sem
   acento, não reproduz o bug em nenhum dos dois modelos. Só as frases exatas do
   briefing reproduzem.

Latência não regrediu apesar do prompt maior (`DICA_ESQUEMA` 267 → 653 chars):
mediana de 3,14 s para 2,74 s no qwen.

**O que a correção não alcançou:** agenda pessoal no qwen continua em
`consultar_pendencias`, 0/5 antes e depois — item novo em "Abertos".

---

## Armadilhas do ambiente (não são bugs do projeto, mas custam tempo)

- **`alembic upgrade head`**: desde o #28 o servidor recusa subir com migração
  pendente. O deploy local do Marcus esquece isso. Lembre nos rascunhos de PR
  que tocam migração.
- **`maestri ask --raw` pelo Bash sofre conversão MSYS**: `"/clear\n"` vira
  `C:/Program Files/Git/clear/n` e entra como texto. Use o tool **PowerShell**
  para `--raw`. Se sujar o input, mande `"\e"` (ESC) antes.
- **Texto longo com `/` pelo Bash também corrompe** (`/comando` vira caminho
  Windows). Grave em arquivo e mande
  `maestri ask "Nome" (Get-Content -Raw <arquivo>)` pelo PowerShell.
- **Heredoc (`<<'EOF'`) falha no tool Bash nesta máquina** ("unexpected EOF") —
  arquivo longo escreve com o tool Write.
- **`cargo test` não roda no CI.** Os 20 testes Rust do microfone passam só na
  máquina local.
- **`gh` não está instalado.** PRs são abertos manualmente pelo Marcus.
- **VRAM**: RTX 4050 com 6 GB. O 7B cabe quase inteiro na GPU; 14B e maiores
  precisariam de offload para a RAM (que sobra: 64 GB). Modelo atual:
  `OLLAMA_MODEL=qwen2.5:7b-instruct` (mediana 1,8–1,9 s contra 3,1 s do
  hermes3:8b, com `SHOGUN_LLM_TIMEOUT=30`).
