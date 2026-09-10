# Produtor de pendências — opções, trade-offs e recomendação

> Documento de decisão, escrito **antes** da implementação. A recomendação
> explícita está na seção 7; o que ela ainda exige de aprovação humana está na
> seção 8.

## 1. O buraco

A leitura de pendências está pronta e usada em produção:

- `GET /pendencias` — o painel do desktop faz polling de 30 s;
- ação `consultar_pendencias` do `POST /comando` — a resposta falada;
- ambas atrás de `PendenciasProvider`, hoje resolvido para
  `ShogunOrquestradorProvider` apoiado no banco (`RepositorioPendencias` sobre
  as tabelas `agentes`/`pendencias`, com migração Alembic aplicada).

A escrita existe, mas **está órfã**. `ShogunOrquestradorProvider` expõe
`registrar_pendencia()`, `atualizar_status()` e `limpar_pendencias()`, e o
`RepositorioPendencias` implementa as três contra o banco — só que **nenhum
caminho do servidor chama qualquer uma delas**. Quem escreve hoje são os
testes. Em produção as tabelas nascem vazias e continuam vazias: o painel
mostra "nenhuma pendência" para sempre, e a fala do Shogun também.

O que falta não é armazenamento nem leitura. É decidir **quem produz**.

## 2. O que já existe, e que qualquer opção deve reaproveitar

| Peça | Onde | Estado |
|---|---|---|
| `Pendencia`, `StatusAgente`, `PendenciasProvider` (ABC, **só leitura**) | `server/app/domain/pendencias.py` | pronto |
| `registrar_pendencia` / `atualizar_status` / `limpar_pendencias` | `ShogunOrquestradorProvider` | pronto, sem chamador |
| `RepositorioPendencias` (`listar`, `status_do_agente`, `registrar`, `atualizar_status`, `limpar`) | `server/app/db/repositorio.py` | pronto |
| Tabelas `agentes` / `pendencias` | `server/app/db/models.py` + migração | prontas |
| Autenticação Bearer por token fixo | `core/security.py` | pronta |
| Rate limit por token, baldes `comando` e `leitura` | `core/rate_limit.py` | pronto (não há balde de escrita) |
| Contratos de fio `PendenciaOut` / `PendenciasResponse` | `shared/python` + `shared/ts` | prontos, com teste de paridade no CI |

Duas propriedades do que existe condicionam tudo o que vem abaixo:

1. **`PendenciasProvider` é uma interface de leitura.** Escrever não cabe nela —
   e não deve caber: `MaestriProvider` nunca vai saber gravar. Ver seção 6.
2. **A tabela `pendencias` é um append simples.** `registrar` sempre faz
   INSERT; não há chave única, e o modelo de domínio `Pendencia` **não tem id**.
   A única forma de fechar algo hoje é `limpar(agente_id)`, que apaga a fila
   inteira do agente. Isso não é acidente: é a semântica que o domínio já
   escolheu, e ela empurra a decisão da seção 5.

## 3. As opções

### A. Rotina interna do servidor (auto-observação)

Um job no `lifespan` observa o estado do próprio servidor (LLM caído, migração
pendente, sessão sem resposta) e registra pendências.

- **Quem autentica:** ninguém — roda em processo, não atravessa fronteira.
- **Duplicidade:** o pior caso de todos. Um laço a cada 30 s reinsere a mesma
  condição a cada tique; sem chave de dedup — que o schema não tem — a tabela
  cresce sozinha até virar ruído.
- **Ciclo de vida:** o melhor de todos. Quem abriu sabe quando a condição
  sumiu, então a própria rotina fecha (`limpar_pendencias`). É a única opção
  com resolução automática.
- **Custo:** médio. Agendador no lifespan, catálogo de condições observáveis,
  e uma chave de dedup nova.
- **Problema de fundo:** produz pendências **sobre o servidor Shogun**, não
  sobre os agentes do Maestri. `consultar_pendencias` responde "o que os
  agentes estão devendo" (ver `docs/AGENTS.md`); saúde do servidor é outra
  pergunta, e misturar as duas na mesma fila polui a fala e o painel. **Não
  preenche o buraco da seção 1.**

### B. Endpoint de escrita (`POST`/`PUT /pendencias`)

O próprio agente reporta o que está devendo, por HTTP. É a opção que casa com
quem os "agentes" são hoje: terminais do Maestri (o coordenador e os agentes de
papel), processos que já sabem falar HTTP e já têm o token.

- **Quem autentica:** o Bearer que já existe, sem nada novo. **Ressalva
  importante:** o token é único e compartilhado, então `agente_id` é
  **auto-declarado e não verificado** — qualquer portador do token pode
  escrever como qualquer agente, inclusive apagar a fila de outro. Em servidor
  de usuário único atrás de Tailscale isso é aceitável; deixa de ser no dia em
  que o token for entregue a um terceiro. Autenticação por agente (um token por
  agente, ou mTLS) é trabalho separado e não é pré-requisito.
- **Duplicidade:** depende da semântica escolhida — é a sub-decisão da seção 5.
- **Ciclo de vida:** o produtor fecha. `limpar_pendencias` e `atualizar_status`
  já existem no provider para isso.
- **Custo:** **baixo.** Uma rota, uma interface de escrita no domínio, um
  contrato de entrada em `shared/` (com a interface TS gêmea, senão o
  `test_paridade_contratos.py` reprova no CI), um balde de rate limit de
  escrita, e testes. Sem migração, sem mudança no schema, sem tocar no caminho
  de leitura.

### C. Webhook do Maestri

O Maestri empurra eventos de agente para o Shogun.

- **Quem autentica:** não pode ser o Bearer de cliente — quem chama é máquina
  externa. Exigiria segredo próprio de webhook, idealmente HMAC do corpo.
- **Duplicidade:** entrega *at least once* é o normal em webhook. Chave de
  idempotência por evento passa de desejável a **obrigatória**.
- **Ciclo de vida:** do Maestri, e só funciona se ele emitir também o evento de
  resolução. Se emitir só "abriu", nada fecha e a fila nunca esvazia.
- **Custo:** alto e **bloqueado**. O Maestri não tem webhook hoje (a API sequer
  está definida — ver `MaestriProvider`), e o Shogun não é alcançável de fora
  da Tailscale, o que a entrega de webhook exigiria.

### D. `MaestriProvider` — o Shogun puxa da API do Maestri

A opção conceitualmente mais limpa: pendência de agente do Maestri mora no
Maestri, e o Shogun só lê.

- **Quem autentica:** o Shogun, ao chamar o Maestri (chave em `Settings`). Não
  há entrada para autenticar — não há entrada.
- **Duplicidade:** não existe. A fonte da verdade é externa e cada leitura é um
  retrato; nada é gravado.
- **Ciclo de vida:** inteiramente do Maestri. O Shogun nunca abre nem fecha.
- **Custo:** **bloqueado.** A API não existe. Quando existir, o custo é o menor
  possível: preencher os dois métodos do stub e trocar a injeção em
  `get_pendencias_provider` — nenhuma rota muda. É o que a interface foi feita
  para permitir.
- **Efeito colateral a registrar:** se D virar a fonte, `registrar_pendencia` e
  as tabelas locais viram cache ou lixo. Ter as duas fontes ao mesmo tempo
  exigiria um provider composto, que não existe e teria que decidir como
  mesclar e como desempatar ordenação.

### E. Escrita direta no banco por processo local (CLI/script)

Um utilitário importa `RepositorioPendencias` e grava sem passar pelo servidor.

- **Quem autentica:** permissão de arquivo, e nada mais.
- **Duplicidade:** a mesma de B, sem sequer uma rota onde validar entrada.
- **Ciclo de vida:** manual.
- **Custo:** o menor de todos — mas com três defeitos que o desqualificam como
  caminho oficial: é um **segundo escritor no mesmo SQLite** do servidor em
  execução (contenção de lock), **só funciona na mesma máquina** (os agentes do
  Maestri nem sempre estarão), e **desvia de validação e rate limit**. Serve
  como ferramenta de depuração, não como produtor.

## 4. Comparação

| | Autenticação | Idempotência | Quem fecha | Custo | Disponível hoje |
|---|---|---|---|---|---|
| A. Rotina interna | n/a (em processo) | ruim — exige dedup novo | a própria rotina | médio | sim, mas **responde outra pergunta** |
| B. Endpoint de escrita | Bearer existente (`agente_id` auto-declarado) | boa, se declarativa (§5) | o produtor | **baixo** | **sim** |
| C. Webhook | segredo/HMAC novo | exige chave de evento | o Maestri (se emitir) | alto | **não** — bloqueado |
| D. Pull do Maestri | Shogun→Maestri | n/a | o Maestri | baixo, quando existir | **não** — bloqueado |
| E. Escrita local | filesystem | ruim | manual | mínimo | sim, mas inadequado |

## 5. Sub-decisão: o que é uma pendência no fio?

Escolher B não basta — falta dizer o que uma escrita significa. Há duas formas,
e elas produzem contratos diferentes para os clientes.

**B1 — log de eventos (`POST` que acrescenta).** Cada chamada insere uma linha.

- Não é idempotente: um produtor que faça retry (ou um laço de polling)
  duplica. Um agente que reporte "estou travado" a cada 30 s cria ~2 880 linhas
  por dia.
- Fechar **uma** pendência exige um id por pendência — que o domínio não tem.
  Introduzi-lo mexe em `Pendencia`, em `PendenciaOut`, na interface TS e no
  caminho de leitura. Sem id, fechar só dá no atacado (`DELETE` do agente
  inteiro), o que é grosso demais para ser útil.

**B2 — estado declarado (`PUT` que substitui).** O agente declara a fila dele
**inteira**, e a chamada substitui o que havia daquele agente.

```
PUT /pendencias/{agente_id}
{
  "agente_nome": "agente-contratos",
  "status": "travado",
  "pendencias": [
    {"descricao": "Esperando decisao do produtor", "prioridade": 5},
    {"descricao": "Revisar contrato de escrita", "prioridade": 0}
  ]
}
```

- **Idempotente por construção.** Mandar duas vezes dá exatamente o mesmo
  estado; retry é seguro sem chave de idempotência nenhuma.
- **Fechar é trivial e não precisa de id:** manda a lista sem o item.
  `"pendencias": []` com `"status": "concluido"` é "não devo nada".
- **Não precisa de `DELETE`** — a lista vazia já é a remoção. A superfície fica
  em **uma** rota.
- Casa com o que o provider já expõe (`limpar_pendencias` + `registrar_pendencia`
  + `atualizar_status`), sem id novo, sem migração, sem tocar na leitura.
- **Custo real 1 — perde histórico.** O `replace` apaga as linhas anteriores.
  Ninguém lê histórico de pendência hoje; se um dia precisar, é tabela de
  eventos separada, não este endpoint.
- **Custo real 2 — a substituição precisa ser atômica.** Hoje `limpar` faz
  commit e cada `registrar` faz o seu; um leitor no meio veria a fila vazia.
  A correção é barata e é de domínio/repositório: um método
  `substituir(agente_id, nome, status, pendencias)` com **um** commit.
- Ponto aberto menor: `status` aparece no agente e em cada `Pendencia` do
  domínio. Proposta: `status` por item é **opcional** e assume o do agente —
  o corpo fica sem redundância e o domínio continua fiel.

**B2 é o recomendado.** É a única forma que resolve idempotência **e** ciclo de
vida sem inventar id, sem migração e sem alargar a superfície de rotas — e é a
que o domínio já estava pedindo, já que `limpar_pendencias` só existe porque
"a fila do agente é substituída" sempre foi a ideia.

## 6. Escrever não cabe em `PendenciasProvider`

`PendenciasProvider` é a interface de **leitura**, e `MaestriProvider` a
implementa sem nunca poder gravar. Uma rota de escrita que dependesse de
`get_pendencias_provider` receberia um objeto sem `registrar_pendencia` — erro
em tempo de execução no dia em que a injeção mudar para o Maestri.

O caminho certo é um **segundo contrato no domínio**, ex.:

```python
class PendenciasEscritor(Protocol):
    def substituir(self, agente_id, agente_nome, status, pendencias) -> None: ...
```

implementado por `ShogunOrquestradorProvider` (que já tem as três primitivas) e
**não** por `MaestriProvider`, com uma dependência própria
(`get_pendencias_escritor`) em `core/pendencias.py`. Leitura e escrita passam a
poder ter fontes diferentes — que é exatamente o cenário provável: ler do
Maestri, escrever no orquestrador local.

Isto é decisão de domínio, dentro do escopo do agente-contratos.

## 7. Recomendação

**Adotar B com a semântica B2: uma rota `PUT /pendencias/{agente_id}`
declarativa, atrás do Bearer que já existe, escrevendo por um contrato de
domínio novo (`PendenciasEscritor`) implementado pelo
`ShogunOrquestradorProvider`.**

Por quê, em uma linha cada:

- **A** responde outra pergunta (saúde do servidor ≠ pendência de agente) e é a
  pior em duplicidade;
- **C** e **D** estão bloqueadas em terceiro que ainda não existe — e D continua
  sendo o **destino** certo, que a interface já deixa livre;
- **E** é um segundo escritor no mesmo SQLite, só local, sem validação;
- **B2** custa pouco, é idempotente por construção, resolve o ciclo de vida sem
  id novo e sem migração, e não fecha nenhuma porta: no dia em que a API do
  Maestri existir, a leitura troca de provider e a escrita local continua
  válida para os agentes que não vivem no Maestri.

Escopo estimado, em commits atômicos:

1. `feat(server)`: contrato `PendenciasEscritor` + `substituir()` no
   `ShogunOrquestradorProvider` e no `RepositorioPendencias` (um commit, um
   único commit de banco);
2. `feat(shared)`: contrato de entrada em `shared/python` + interface gêmea em
   `shared/ts` (o teste de paridade exige as duas pontas);
3. `feat(server)`: rota `PUT /pendencias/{agente_id}` + dependência
   `get_pendencias_escritor` + balde de rate limit de escrita;
4. `test(server)`: idempotência, substituição, lista vazia, 401, agente
   desconhecido;
5. `docs`: `CONTEXTO-GERAL.md` (some a lacuna "nenhum produtor de pendências") e
   `ROADMAP.md`.

## 8. O que **não** está decidido aqui

Três pontos são de arquitetura e precisam de aval humano antes da
implementação:

1. **B1 vs B2** define o que é uma pendência no fio, e cria contrato
   compartilhado que desktop e mobile vão consumir. A recomendação é B2, mas a
   escolha é da coordenação.
2. **Contrato de escrita separado no domínio** (`PendenciasEscritor`) — divide
   `PendenciasProvider` em duas interfaces com fontes potencialmente
   diferentes.
3. **`agente_id` auto-declarado sob token compartilhado** é aceito
   conscientemente, não esquecido. Se a resposta for "não aceito", a opção B
   passa a exigir autenticação por agente, e o custo deixa de ser baixo.

Um ponto de processo: implementar a rota é território do **agente-backend**
(`server/app/api/`); o agente-contratos responde pelos itens 1 e 2 do escopo
(domínio, repositório e contratos). A divisão do trabalho entre os dois é da
coordenação.
