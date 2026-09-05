# Banco de dados

**Decisão: SQLite via SQLAlchemy.**

**Nada disto está implementado.** É o desenho do schema que sustenta os passos 3
e 8 do [fluxo de uma mensagem](DESIGN.md). O servidor hoje não tem persistência
nenhuma: `session_id` chega no request e volta na resposta sem nunca ser gravado.

## Por que SQLite

**Zero infraestrutura.** O banco é um arquivo; não há serviço para subir,
configurar ou manter. Quem clona o repositório roda `uvicorn` e pronto — mesmo
espírito da escolha do Ollama para o LLM: o projeto funciona inteiro na máquina
do Marcus, sem depender de nada externo.

**Latência mínima.** Sem round-trip de rede: a leitura do histórico (passo 3) é
uma chamada de função, não uma ida a outro processo. Num fluxo que já vai gastar
segundos esperando o modelo, o banco não deve somar nada perceptível.

**A carga é de um usuário falando um comando por vez.** Nenhuma vantagem de um
banco de rede é exercida hoje.

## Por que SQLAlchemy

Sem ele a decisão acima seria cara de reverter: SQL escrito à mão para SQLite
espalha dialeto pelo código todo, e trocar de banco viraria uma revisão de cada
query.

Com SQLAlchemy, os modelos e as queries são escritos uma vez e o dialeto é
resolvido pela connection string. É a mesma estratégia que `LLMProvider` e
`PendenciasProvider` já aplicam no projeto: **a decisão concreta fica atrás de
uma interface, e trocá-la não reescreve quem a usa.**

Vale manter também o acesso ao banco atrás de um repositório — as rotas pedem "o
histórico desta sessão", não montam query. Assim nem a escolha do ORM vaza para
a camada HTTP.

## Schema

Duas tabelas. A regra do corte: só entra campo que algum passo do fluxo precisa.

### `sessions`

Uma conversa. Criada no passo 3 quando o `session_id` gerado pelo cliente chega
pela primeira vez.

| Campo | Tipo | Papel |
| --- | --- | --- |
| `id` | TEXT (PK) | o `session_id` do `CommandRequest` — gerado no cliente (passo 2) |
| `created_at` | TIMESTAMP | quando a sessão começou |
| `updated_at` | TIMESTAMP | última mensagem; atualizado no passo 8 |

`updated_at` é o que permite listar sessões por atividade e expirar as antigas —
por isso é campo, não algo derivado de `MAX(messages.created_at)` a cada consulta.

### `messages`

Uma fala, do Marcus ou do Shogun. Usada pelos passos 3 (INSERT do usuário e
SELECT do histórico) e 8 (INSERT do assistente).

| Campo | Tipo | Papel |
| --- | --- | --- |
| `id` | INTEGER (PK, autoincrement) | ordem de inserção — é a ordenação canônica |
| `session_id` | TEXT (FK → `sessions.id`) | a conversa a que pertence |
| `role` | TEXT | `user` ou `assistant` |
| `content` | TEXT | o texto da fala |
| `created_at` | TIMESTAMP | quando entrou |

Índice em `(session_id, id)`: é exatamente a consulta do passo 3 — as últimas N
mensagens de uma sessão, em ordem.

A ordenação é por `id`, não por `created_at`: duas mensagens gravadas no mesmo
instante não teriam desempate por timestamp, e a ordem user → assistant dentro de
um comando precisa ser estável.

### Campos deliberadamente fora

Não entram agora, mas o gatilho de cada um já é conhecido:

- **`provider`** em `messages` (qual LLM respondeu) — sem isso não dá para saber
  depois se uma resposta ruim veio do modelo local ou do fallback de nuvem.
  Entra junto com o passo 8.
- **`acao` / `parametros`** — hoje reconstruíveis do texto; viram necessários se
  o histórico precisar alimentar o modelo com as ações passadas.
- **`tokens`** — só faz sentido se a janela do passo 4 for por orçamento de
  tokens em vez de contagem de mensagens.
- **`user_id`** em `sessions` — ver os critérios de migração abaixo; múltiplos
  usuários e Postgres tendem a chegar juntos.

---

# Critérios de migração futura para Postgres

Esta seção é o roteiro para quando alguém for instruído a "iniciar a migração
para Postgres". A decisão por SQLite **não** foi por falta de análise: foi por
adequação ao uso atual. O que segue é o que muda esse uso.

## Gatilhos

Qualquer um destes justifica reabrir a decisão. Nenhum vale hoje.

1. **Deploy em servidor remoto acessível externamente.** O arquivo SQLite mora no
   disco do processo. Sai da máquina do Marcus, some a premissa de "banco local"
   — e com acesso externo vêm backup, retenção e controle de acesso, que um
   arquivo não resolve sozinho.
2. **Múltiplos usuários simultâneos.** Deixa de ser um comando por vez. Traz
   junto `user_id` em `sessions` e a verificação de posse que o passo 2 do
   [DESIGN.md](DESIGN.md) hoje dispensa.
3. **Necessidade de acesso concorrente real.** SQLite serializa escritas: um
   escritor por vez, e o servidor é `async`. Escritas concorrentes viram
   `database is locked` sob carga. O sinal prático é esse erro aparecendo em log,
   ou mais de um processo/worker precisando escrever no mesmo banco.
4. **Volume comprometendo a performance.** Histórico crescendo a ponto de o
   SELECT do passo 3 pesar mesmo com índice, ou o arquivo ficando grande demais
   para backup por cópia.

Um quinto, de natureza diferente: **busca semântica no histórico**. Se a memória
de longo prazo virar requisito, `pgvector` decide sozinho — não há equivalente
maduro em SQLite, e migrar por esse motivo evita trocar de banco duas vezes.

## O que o SQLAlchemy resolve — e o que não resolve

**Resolve:** os modelos declarativos e as queries do ORM são independentes de
dialeto. Trocar `sqlite:///shogun.db` por `postgresql+asyncpg://...` na variável
de ambiente basta para o grosso do código, sem reescrever query nenhuma.

**Não resolve, se descuidado desde o início.** A portabilidade é consequência de
escrever assim, não do ORM por si:

- **SQL cru é dívida direta.** Cada `text("...")` precisa ser revisado à mão.
- **Tipos específicos de dialeto** (`sqlite.JSON`, `postgresql.JSONB`) prendem ao
  banco. Usar os tipos genéricos de `sqlalchemy.types` enquanto der.
- **Autoincrement**: `INTEGER PRIMARY KEY` do SQLite e `SERIAL`/`IDENTITY` do
  Postgres se comportam diferente. Declarar como `Integer, primary_key=True` e
  deixar o dialeto resolver.
- **Timestamps**: SQLite não tem tipo de data nativo (guarda texto) e ignora
  fuso; Postgres tem `timestamptz`. **Gravar sempre em UTC desde o primeiro dia**
  — é o único item desta lista que, se ignorado, corrompe dados já gravados em
  vez de só dar trabalho na hora.
- **Migrações**: adotar Alembic junto com o schema inicial, não depois. Sem ele
  não existe "migrar o schema" — existe recriá-lo e torcer.

## Checklist da migração

Roteiro de alto nível. **Não executar agora.**

1. **Provisionar o Postgres** — instância, credenciais, acesso de rede e política
   de backup. Definir se é serviço gerenciado ou container próprio.
2. **Migrar o schema** — rodar as migrações Alembic contra o banco novo e
   conferir o resultado contra o schema acima (tipos, constraints, o índice
   `(session_id, id)`).
3. **Migrar os dados existentes** — exportar `sessions` e `messages` do arquivo
   SQLite e carregar no Postgres, preservando os `id` de `messages` (a ordenação
   canônica depende deles). Conferir contagem por tabela e a mensagem mais
   recente de cada sessão.
4. **Atualizar a variável de conexão** — `DATABASE_URL` em `core/config.py`,
   `.env.example` e no ambiente de execução. Trocar o driver para um async
   (`asyncpg`) e acrescentá-lo a `requirements.txt`.
5. **Testar em staging antes de produção** — subir uma cópia apontando para o
   Postgres, rodar a suíte inteira e exercitar o fluxo real do
   [DESIGN.md](DESIGN.md) de ponta a ponta: sessão nova, várias mensagens,
   histórico recuperado corretamente entre reinícios.
6. **Trocar em produção** — com o SQLite guardado como rollback até a nova
   configuração acumular uso real.

Ordem importante: os passos 1-3 não afetam o servidor em execução. O corte
acontece só no 4.
