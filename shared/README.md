# shared

Tipos e contratos compartilhados entre o servidor e os clientes.

```
shared/
├── contracts/   # vazio (ver abaixo)
├── ts/          # tipos TypeScript (desktop e mobile)
└── python/      # modelos Pydantic (server) — fonte da verdade hoje
```

## Convenção de nomes: `snake_case` no fio

Os campos trafegam exatamente como os modelos Pydantic os declaram —
`session_id`, não `sessionId`. Não há `alias_generator` em `shared/python`, e os
tipos de `shared/ts` declaram os mesmos nomes.

Isso descreve o **JSON na rede**, não o estilo do código do cliente: um cliente
TS pode chamar a variável de `sessionId` internamente; o que ele não pode é
esperar `sessionId` no corpo da resposta.

## ⚠️ `contracts/` está vazio

O plano era `contracts/` guardar os JSON Schema e **derivar** dali os tipos TS e
os modelos Pydantic, para que os dois lados não pudessem divergir. Isso nunca foi
construído: a pasta só tem um README.

Na prática, quem manda hoje é `python/` — é o que o servidor executa e o que os
testes cobrem. `ts/` é mantido à mão, em espelho.

E foi exatamente por aí que a primeira divergência apareceu: `ts/` declarava
`sessionId` enquanto o servidor emitia `session_id`, e nada acusou — os dois
clientes descobriram em runtime, cada um por conta própria. Enquanto a geração a
partir de schema não existir, **mexer em um lado obriga a mexer no outro no mesmo
commit.**

## Como os clientes consomem estes tipos

`desktop/` e `mobile/` importam de `shared/ts` por **caminho relativo**, e
sempre com `import type`:

```ts
import type { CommandResponse } from "../../../shared/ts";
```

Nao ha workspace de npm, alias de tsconfig nem symlink — e nao precisa haver.
`import type` e apagado na compilacao: nada do `shared/` chega ao bundle, entao
nem o Vite (desktop) nem o Metro (mobile) precisam resolver esse caminho. Quem
resolve e so o TypeScript, direto do sistema de arquivos.

Foi uma decisao deliberada de nao introduzir estrutura. As alternativas custam
bem mais:

| Alternativa | Custo |
|---|---|
| npm workspaces na raiz | `package.json` raiz novo, `package.json` para `shared/ts`, node_modules hoistado e reinstalacao nos dois clientes. O Expo ainda exigiria `watchFolders` no Metro |
| alias de tsconfig + bundler | `paths` no tsconfig **e** alias no Vite **e** `metro.config.js` com `watchFolders` — tres configuracoes para manter em sincronia |
| caminho relativo com `import type` | nenhuma configuracao |

**A regra que sustenta isso: os contratos sao tipos, nunca valores.** Nada em
`shared/ts` pode virar `const`, `enum` ou funcao — no momento em que virar, o
`import type` deixa de bastar, o bundler passa a precisar resolver o caminho, e
a tabela acima volta a valer. Se precisar de valor compartilhado, decida a
estrutura antes.
