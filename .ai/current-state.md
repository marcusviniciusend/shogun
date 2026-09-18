# L1 — Estado atual

_Atualizado em 2026-09-18. Atualize a data sempre que mexer aqui._

## Onde o projeto está

- **v1.0 do desktop: entregue.** 36 PRs mergeados em `dev` (#1–#36). O Shogun
  fala (TTS), executa apps (`ClientInstruction`), tem histórico de conversas
  navegável, rate limit, consumo com preço e orquestrador persistente.
- **v1.1 em andamento: STT / ditado.** Branch
  `feature/desktop-ditado-clique-medidor` — 7 commits, empurrada, **PR ainda não
  aberta**. Ícone de microfone, ditado por clique-alterna e medidor de nível ao
  vivo.
- **Streaming ficou fora da v1.0** por decisão registrada em
  `docs/streaming-design.md` (#35). Desenho escolhido para depois: streaming do
  campo final.
- **Mobile congelado** até pós-v1.0 do desktop. Plano de descongelamento
  aprovado no PR #17; ordem: token seguro → chat texto → Config → histórico →
  STT/TTS.

## Branch atual

`feature/desktop-ditado-clique-medidor` (à frente de `origin/dev`).
Não commitado no momento: `desktop/src-tauri/Cargo.toml` modificado,
`server/semear.py` e `.claude/` sem rastreio.

## Suíte

231 passed no fechamento da v1.0. Rode antes de confiar neste número —
ele envelhece.

## O que vem a seguir

Plano completo em [`.maestri/proximas-rodadas.md`](../.maestri/proximas-rodadas.md).
Resumo do que está em aberto:

1. **Fechar a v1.1** — dois bugs abertos (F10.10 e F10.15, ver
   [`known-issues.md`](known-issues.md)) e 12 passos do
   `docs/roteiro-ditado.md` ainda não conferidos: F10.3, F10.6, F10.11–F10.14,
   F10.16, F10.17, mais F10.7/F10.8/F10.9/F10.19 (reescritos quando o gesto
   virou clique, precisam de nova passada).
2. **Rodada 8 (qualidade/segurança)** — sanitizar `str(exc)` vazando ao cliente
   nas respostas de erro; produtor de pendências (o orquestrador persistente
   #27/#29 está pronto e vazio: nada chama `registrar_pendencia`).
3. **Cerimonial da v1.0** — PR `dev` → `main` + tag `v1.0.0`. Só o Marcus.
4. **Timing do descongelamento do mobile** — decisão do Marcus, pendente.

## Log vivo da coordenação

`.maestri/status-geral.md`. Rascunhos de PR em `.maestri/pr-pendente-*.md`.
