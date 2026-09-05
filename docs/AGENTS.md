# Agentes do Shogun (`server/app/agents/`)

## Aviso de nomenclatura: dois "agentes" diferentes

A palavra aparece em dois sentidos neste repositório, e eles não têm relação:

| | **Agentes do Shogun** | **Agentes do Maestri** |
| --- | --- | --- |
| O que são | módulos de código dentro do produto | instâncias de Claude Code escrevendo o produto |
| Onde vivem | `server/app/agents/` | fora do repositório, no canvas do Maestri |
| Quando rodam | em produção, atendendo o Marcus | durante o desenvolvimento |
| Quem invoca | o orquestrador, a partir de um comando de voz | o Marcus, distribuindo tarefas |
| Exemplos | agente de sistema, de agenda, de busca | `agente-backend`, `agente-contratos`, `agente-desktop` |
| Duram | enquanto o Shogun existir | o tempo de uma tarefa |

**Este documento trata só dos primeiros.** Os agentes do Maestri são andaimes de
desenvolvimento: aparecem em `CLAUDE.md` e no histórico do git, nunca no código
que roda para o usuário final.

A confusão tem uma armadilha concreta: `consultar_pendencias` consulta pendências
**dos agentes do Maestri** (via `PendenciasProvider`). É uma ação do Shogun que
por acaso fala sobre o outro tipo de agente — não é um agente do Shogun chamando
outro. O `MaestriProvider` é um cliente de API externa, não um agente.

## Estado atual

A pasta tem `__init__.py` e um `README.md` de três linhas. Nenhum agente foi
escrito ainda, e o roteamento hoje é um `if/elif` na rota `/comando`:

```python
if intencao.acao == "consultar_pendencias":
    ...
elif intencao.acao == "abrir_app":
    ...
```

Isso é adequado para três ações e deixa de ser quando forem dez — é o ponto em
que a pasta passa a existir de verdade.

## O papel que a pasta deve cumprir

Um agente é **o que executa uma ação depois que o modelo já interpretou a
intenção**. Ele não conversa com o LLM e não decide o que fazer: recebe uma
intenção pronta e devolve um resultado estruturado.

```
comando ──▶ LLMProvider ──▶ ComandoInterpretado ──▶ agente ──▶ AgentAction
            (decide o quê)   acao + parametros      (faz)      (resultado)
```

A divisão de responsabilidade que isso preserva: **o LLM decide, o agente faz.**
Um agente que chama o modelo de novo por conta própria quebra a separação e torna
o custo de um comando imprevisível.

### Contrato sugerido

Espelhando o que já funcionou em `LLMProvider` e `PendenciasProvider` — um
`Protocol` estreito, implementações registradas num dicionário, injeção por
`Depends`:

```python
class Agente(Protocol):
    nome: str  # aparece em AgentAction.agent e nos logs

    async def executar(self, intencao: ComandoInterpretado) -> ResultadoAgente:
        """Executa a ação já interpretada. Nunca levanta: falha vira resultado."""
```

Onde `ResultadoAgente` carrega a fala (`resposta_falada` ajustada) e a
`AgentAction` que vai para o cliente.

Três propriedades que o código atual já pratica e que os agentes devem manter:

1. **Falha de integração externa não derruba o comando.** `_consultar_pendencias`
   captura tudo e devolve `AgentAction(status="error")` — o Shogun responde "não
   consegui consultar agora" em vez de estourar um 500.
2. **I/O síncrono vai para a threadpool.** `run_in_threadpool` já é usado para não
   travar o event loop enquanto outros comandos são atendidos.
3. **Registro em dicionário, não `if/elif`.** `acao` → agente, do mesmo jeito que
   `PROVIDERS` mapeia nome → provedor. Adicionar ação passa a ser uma entrada
   nova, sem tocar na rota.

Uma diferença em relação a `LLMProvider`: as ações suportadas são um `Literal`
fechado em `base.py`, e o schema enviado ao modelo é derivado dele. Um agente novo
não é só uma classe nova — é também uma entrada no enum `ACOES`, senão o modelo
nunca escolherá aquela ação.

## Agentes previstos

Os nomes vêm do diagrama da arquitetura; nenhum existe ainda.

| Agente | Faz | Depende de |
| --- | --- | --- |
| sistema | abrir apps, controlar o SO | contrato com o cliente — o servidor não tem acesso ao SO do Marcus (é a pendência do `abrir_app` hoje) |
| agenda | consultar e criar compromissos | escolher a fonte (Google Calendar, arquivo local) |
| busca | pesquisar na web e resumir | escolher o provedor de busca |

O de sistema tem uma restrição que os outros não têm e que precisa ficar
explícita: **o servidor pode rodar em outra máquina**. Ele não executa a ação —
devolve ao cliente a instrução do que abrir, e o cliente executa. Por isso
`abrir_app` continua placeholder: falta o contrato, não a implementação.

## Relação com o resto

- [DESIGN.md](DESIGN.md) — onde os agentes entram no fluxo (passo 7)
- [architecture.md](architecture.md) — visão geral dos componentes
