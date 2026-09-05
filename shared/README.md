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
