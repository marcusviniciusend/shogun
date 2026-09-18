# `.ai/` — camada de contexto e memória

Contexto estruturado para os agentes do canvas Maestri. Existe para **evitar
que cada agente releia o repositório inteiro** a cada tarefa.

Regra de ouro: **isto aponta, não duplica.** A fonte da verdade continua sendo
`CLAUDE.md`, `docs/` e o próprio código. Se um arquivo daqui contradisser a
fonte, a fonte ganha e o arquivo daqui está desatualizado — corrija-o.

## Os três níveis

| Nível | O que é | Tamanho | Onde vive |
|-------|---------|---------|-----------|
| **L0 — Task Context** | A tarefa atual e o objetivo. Efêmero, morre com a tarefa. | pequeno | nota `L0 — Tarefa Atual` no canvas Maestri (não em arquivo) |
| **L1 — Project State** | Estado, decisões e convenções do projeto. | médio | `current-state.md`, `decisions.md`, `conventions.md`, `known-issues.md` |
| **L2 — Repository Knowledge** | Conhecimento do repositório: arquitetura, módulos, grafo. | focado | `architecture.md`, `modules/*.md`, `graphify-out/` |

## Quem lê o quê

| Agente | Lê | Por quê |
|--------|-----|---------|
| **Scout** (descoberta) | L0 + L1 | Localiza arquivos e dependências; não precisa do desenho todo. |
| **Architect** (desenho) | L0 + L1 + L2 | Propõe solução e avalia impacto — precisa do mapa. |
| **Coder** (implementação) | L0 + L1 + L2 (só os módulos tocados) | Escreve o código seguindo padrão. |
| **Tester** (validação) | L0 + L1 | Roda suíte e confere cobertura; padrão de teste está em L1. |
| **Reviewer** (revisão) | L0 + L1 + `git diff` | Revisa a mudança, não o repositório. |

**Git é contexto primário** para Coder, Tester e Reviewer: `git diff`,
`git status`, `git log -n 5` e a lista de arquivos alterados dizem mais, e mais
barato, que qualquer varredura. **Graphify** é o L2 navegável: o grafo já está
construído em `graphify-out/`, e a forma de consultá-lo é
`graphify query "<pergunta>"` — não varredura, e não o portal. O portal
`Portal` no canvas mostra o mesmo grafo em HTML e serve para o Marcus olhar.

## Quem atualiza o quê

Atualizar é parte da tarefa, não faxina posterior:

- **Architect** → `decisions.md` (toda decisão de desenho que sobrevive à tarefa)
  e `architecture.md` quando a estrutura muda.
- **Coder** → `modules/*.md` quando um módulo ganha ou perde responsabilidade.
- **Tester** → `known-issues.md` (bug achado e não corrigido entra aqui, com o
  motivo de não ter sido corrigido).
- **Reviewer** → `current-state.md` ao fechar uma rodada.
- Ninguém edita `conventions.md` sem que `CLAUDE.md` mude junto.

Entrada nova em `decisions.md` e `known-issues.md` é **append no topo**, com
data absoluta. Nada de "ontem" ou "na semana passada".
