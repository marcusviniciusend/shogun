# Schemas JSON dos contratos

**Vazio.** A ideia é esta pasta guardar os JSON Schema dos contratos e os tipos
de `../ts` e os modelos de `../python` serem *derivados* daqui — para que server
e clientes não possam sair de sincronia.

Nada disso foi construído. Hoje a fonte da verdade é `../python` (Pydantic), que
é o que o servidor executa, e `../ts` é espelho mantido à mão.

O custo de não ter isso já apareceu uma vez: `ts/` declarou `sessionId` enquanto
o servidor emitia `session_id`, e a divergência só foi notada quando dois
clientes bateram nela em runtime.
