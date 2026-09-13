/**
 * Testes do F9.2 — quais status de agente ganham o bengara.
 *
 * `STATUS_CRITICOS` e um `Set<string>` e a comparacao e `has(p.status)`: o
 * `tsc` nao tem o que checar. Um status renomeado no servidor (o enum
 * `StatusAgente`, espelhado em `shared/ts`) nao quebra compilacao nenhuma — o
 * "travado" simplesmente para de ficar vermelho, em silencio, e o painel passa
 * a mostrar um agente travado com a mesma cor de um executando. E o mesmo tipo
 * de acoplamento por string que `instrucoes.escopo.test.ts` fecha entre o mapa
 * de apps e o capabilities do Tauri.
 *
 * Por isso a lista de status e lida do `shared/ts` como TEXTO: a uniao de
 * literais some na compilacao e nao existe em tempo de execucao, entao ler o
 * arquivo e a unica forma de o teste falhar quando o contrato muda.
 */
import { describe, expect, it } from "vitest";

// `?raw` traz o arquivo como texto pelo proprio Vite — mesma ideia do import
// de JSON em `instrucoes.escopo.test.ts`, e sem depender de API do Node.
import CONTRATO_TS from "../../../shared/ts/index.ts?raw";
import type { PendenciaWire } from "../lib/types";
import { STATUS_CRITICOS } from "./PainelAgentes";

type Status = PendenciaWire["status"];

/**
 * Classificacao esperada, uma entrada por status do contrato.
 *
 * Sendo um `Record<Status, boolean>`, status novo no contrato sem entrada aqui
 * e erro de compilacao — a segunda rede, para quem roda `npm run build`.
 */
const CLASSIFICACAO: Record<Status, boolean> = {
  executando: false,
  pendente: false,
  travado: true,
  erro: true,
  concluido: false,
};

/** Os literais de `status` declarados em `PendenciaOut` (shared/ts). */
function statusDoContrato(): string[] {
  const bloco = CONTRATO_TS.match(/export interface PendenciaOut \{[^}]*\}/);
  if (!bloco) {
    throw new Error(
      "shared/ts/index.ts nao tem mais a interface PendenciaOut — o painel de " +
        "agentes le o status dela.",
    );
  }
  const linha = bloco[0].match(/^\s*status:\s*(.+);$/m);
  if (!linha) {
    throw new Error("PendenciaOut nao declara mais o campo status.");
  }
  return [...linha[1].matchAll(/"([^"]+)"/g)].map((m) => m[1]);
}

const DO_CONTRATO = statusDoContrato();

describe("STATUS_CRITICOS x o enum StatusAgente do servidor", () => {
  it("o contrato ainda declara os status que o painel classifica", () => {
    // Falha quando o servidor renomeia, remove ou acrescenta um status: e o
    // aviso de que a classificacao aqui precisa ser revista.
    expect([...DO_CONTRATO].sort()).toEqual(Object.keys(CLASSIFICACAO).sort());
  });

  it("nenhum status critico ficou orfao do contrato", () => {
    // Um "travdo" digitado errado nao levanta erro nenhum: o `has` so devolve
    // false e a pendencia critica sai neutra.
    const orfaos = [...STATUS_CRITICOS].filter((s) => !DO_CONTRATO.includes(s));

    expect(orfaos).toEqual([]);
  });
});

describe("F9.2 — classificacao de cada status", () => {
  it.each(Object.entries(CLASSIFICACAO))(
    "%s -> critico: %s",
    (status, critico) => {
      expect(STATUS_CRITICOS.has(status)).toBe(critico);
    },
  );

  it("travado e erro sao os unicos criticos", () => {
    expect([...STATUS_CRITICOS].sort()).toEqual(["erro", "travado"]);
  });

  it("pendente e executando ficam neutros — vermelho e so para erro", () => {
    expect(STATUS_CRITICOS.has("pendente")).toBe(false);
    expect(STATUS_CRITICOS.has("executando")).toBe(false);
  });

  it("status desconhecido cai no neutro, nao no vermelho", () => {
    // Servidor mais novo que o cliente: pintar de vermelho o que nao se
    // entende seria alarme falso.
    expect(STATUS_CRITICOS.has("hibernando")).toBe(false);
  });
});
