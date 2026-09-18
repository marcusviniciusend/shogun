# L1 — Problemas conhecidos

Bug achado e **não corrigido** entra aqui, com o motivo de não ter sido
corrigido. Append no topo, data absoluta. Ao corrigir, mova para "Resolvidos"
com o commit/PR.

---

## Abertos

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

### Classificação: horário cai em `consultar_pendencias`
`server/app/core/llm/base.py` · achado em 2026-09-15

A descrição de `consultar_pendencias` no `ESQUEMA_COMANDO` diz só "o Marcus quer
saber o que está pendente" — sem dizer que pendência ali é **status de agente**.
Modelos pequenos associam horário/agenda a "coisas pendentes".

Reproduzido 3/3 com `qwen2.5:7b` **e** com `hermes3:8b`: "Qual o horário agora?"
e "Que horas são em São Luís Maranhão" caem em pendências; "Que horas são?"
sozinho acerta.

**Não é o modelo, é o prompt** — vale para todos os provedores.

### `str(exc)` vaza ao cliente
`server/` · rotas de erro

Detalhe de exceção chega na resposta ao cliente. Deveria ser mensagem genérica
ao cliente e detalhe só no log. Está na rodada 8 de `.maestri/proximas-rodadas.md`.

### Orquestrador persistente pronto e vazio
`server/` · #27/#29

Nada chama `registrar_pendencia`. Falta desenhar quem produz pendência (rotina
interna? webhook? placeholder do Maestri?).

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
