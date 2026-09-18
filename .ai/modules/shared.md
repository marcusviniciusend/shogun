# L2 — Módulo `shared/`

Contratos entre servidor e clientes. **Um contrato só, escrito duas vezes:**
`shared/python` (Pydantic) e `shared/ts` (TypeScript).

```
shared/
  python/__init__.py    # CommandRequest, CommandResponse, AgentAction, ClientInstruction
  ts/index.ts           # os mesmos, em TS
  contracts/README.md
```

## A regra

Toda mudança em um lado exige a mudança equivalente no outro, **no mesmo commit
ou pelo menos na mesma branch**. Nunca "o TS entra no PR seguinte". Vale para:
campo novo, campo removido, mudança de tipo, de opcionalidade, e de
`Literal`/union (por exemplo, um `type` novo em `ClientInstruction`).

Quem impõe: `server/tests/test_paridade_contratos.py`. Ele lê
`shared/ts/index.ts` **como texto** e compara contratos, campos, opcionalidade
e tipos contra os `BaseModel` de `shared/python`. Mexer num lado só **quebra o
CI** — o teste existe para transformar esquecimento em falha barulhenta, não
para ser contornado.

## O ponto cego

Duas coisas do `ClientInstruction` **nenhum tipo representa**, e por isso
nenhum teste de paridade protege:

1. **Regra de consumo:** `text` × `fallback_text` — nunca os dois.
2. **Invariante de segurança:** o servidor manda **só o nome do app**.

As duas vivem nas docstrings dos dois arquivos. Mudar o comportamento sem mudar
as docstrings não quebra teste nenhum — passa a mentir em silêncio.

Rede mecânica delas, que é outra:
- invariante → `server/tests/test_comando.py`
- regra de consumo → `desktop/src/lib/instrucoes.test.ts`
