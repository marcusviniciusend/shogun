/**
 * Testes do F6.3 — a conversao de fuso da lista de Conversas.
 *
 * O banco grava UTC SEM tzinfo (docs/DATABASE.md) e o fio devolve assim:
 * `criada_em`/`atualizada_em` de sessao e mensagem vem sem sufixo, enquanto o
 * `timestamp` de pendencia vem COM "Z". Quem exibe precisa acrescentar o "Z"
 * antes de criar o Date — esquecer nao levanta erro nenhum: o `Date` le a
 * string como hora LOCAL e o relogio sai deslocado (3h no Brasil). Numero
 * plausivel, hora errada, semanas sem ninguem notar. Era o que o roteiro
 * mandava conferir comparando com o relogio de pulso.
 *
 * O fuso e FIXADO por teste (`process.env.TZ`), nunca herdado da maquina:
 * teste de fuso que so passa em quem escreveu nao prova nada. O Node 22 releva
 * a troca em tempo de execucao, entao nao e preciso recarregar o modulo.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { quando } from "./Conversas";

/**
 * O desktop compila para o webview, entao `@types/node` nao esta instalado.
 * Declarar so o que este teste usa evita uma dependencia nova por causa de uma
 * variavel de ambiente.
 */
declare const process: { env: Record<string, string | undefined> };

const TZ_ORIGINAL = process.env.TZ;

/** Fixa o fuso do processo — o que `toLocaleTimeString` sem opcao usa. */
function fixarFuso(tz: string): void {
  process.env.TZ = tz;
}

/** Congela o "agora" num instante UTC conhecido. */
function agoraEm(instanteUtc: string): void {
  vi.useFakeTimers();
  vi.setSystemTime(new Date(instanteUtc));
}

/**
 * O mesmo instante nas duas formas em que ele chega do servidor: sessao (sem
 * sufixo) e pendencia (com "Z"). Em Sao Paulo (UTC-3) e 10/09 as 23:30.
 */
const SEM_Z = "2026-09-11T02:30:00";
const COM_Z = "2026-09-11T02:30:00Z";

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  vi.useRealTimers();
  if (TZ_ORIGINAL === undefined) delete process.env.TZ;
  else process.env.TZ = TZ_ORIGINAL;
});

describe("F6.3 — o sufixo Z e acrescentado antes da conversao", () => {
  it("le o valor do fio como UTC, nao como hora local", () => {
    fixarFuso("America/Sao_Paulo");
    // 17:00 de 10/09 em Sao Paulo: o instante abaixo cai no MESMO dia local,
    // entao o retorno e a hora — que e onde o deslocamento apareceria.
    agoraEm("2026-09-10T20:00:00Z");

    // Sem o sufixo, o Date leria a string como hora local e devolveria 02:30.
    const lidoComoLocal = new Date(SEM_Z).toLocaleTimeString("pt-BR", {
      hour: "2-digit",
      minute: "2-digit",
    });
    expect(lidoComoLocal).toBe("02:30");

    expect(quando(SEM_Z)).toBe("23:30");
    expect(quando(SEM_Z)).not.toBe(lidoComoLocal);
  });

  it("nao acrescenta um segundo Z no que ja veio com Z", () => {
    fixarFuso("America/Sao_Paulo");
    agoraEm("2026-09-10T20:00:00Z");

    // "...ZZ" seria Invalid Date e a celula sairia vazia.
    expect(quando(COM_Z)).toBe("23:30");
  });

  it("as duas formas do fio descrevem o mesmo instante e exibem igual", () => {
    fixarFuso("America/Sao_Paulo");
    agoraEm("2026-09-10T20:00:00Z");

    expect(quando(SEM_Z)).toBe(quando(COM_Z));
  });

  it.each([
    ["America/Sao_Paulo", "2026-09-10T20:00:00Z", "23:30"],
    ["UTC", "2026-09-11T08:00:00Z", "02:30"],
    ["Asia/Tokyo", "2026-09-11T08:00:00Z", "11:30"],
  ])(
    "em %s o mesmo instante UTC sai como %s -> %s no relogio local",
    (tz, agora, esperado) => {
      fixarFuso(tz);
      agoraEm(agora);

      expect(quando(SEM_Z)).toBe(esperado);
    },
  );

  it("aceita os microssegundos que o Pydantic serializa", () => {
    fixarFuso("America/Sao_Paulo");
    agoraEm("2026-09-10T20:00:00Z");

    // Seis casas decimais nao sao ISO 8601 estrito; se o Date recusasse, TODA
    // celula da lista sairia vazia.
    expect(quando("2026-09-11T02:30:00.123456")).toBe("23:30");
  });
});

describe("hoje vira hora, resto vira dia/mes", () => {
  it("conversa de hoje mostra HH:MM", () => {
    fixarFuso("America/Sao_Paulo");
    agoraEm("2026-09-10T20:00:00Z");

    expect(quando(SEM_Z)).toMatch(/^\d{2}:\d{2}$/);
  });

  it("conversa antiga mostra DD/MM", () => {
    fixarFuso("America/Sao_Paulo");
    agoraEm("2026-09-10T20:00:00Z");

    const antiga = quando("2026-07-04T14:00:00");
    expect(antiga).toMatch(/^\d{2}\/\d{2}$/);
    expect(antiga).toBe("04/07");
  });

  it("o corte do dia e o LOCAL, nao o UTC", () => {
    fixarFuso("America/Sao_Paulo");
    // 07:00 de 11/09 em Sao Paulo. O instante da conversa e 11/09 em UTC, mas
    // 10/09 no relogio de quem olha — precisa sair como data, nao como hora.
    agoraEm("2026-09-11T10:00:00Z");

    expect(quando(SEM_Z)).toBe("10/09");
  });

  it("mesmo dia e mes de outro ano nao conta como hoje", () => {
    fixarFuso("America/Sao_Paulo");
    agoraEm("2026-09-10T20:00:00Z");

    // Comparar so dia e mes e o erro classico: 10/09/2025 viraria "17:00".
    expect(quando("2025-09-10T20:00:00")).toBe("10/09");
  });

  it("mesmo dia do mes em mes diferente nao conta como hoje", () => {
    fixarFuso("America/Sao_Paulo");
    agoraEm("2026-09-10T20:00:00Z");

    expect(quando("2026-08-10T20:00:00")).toBe("10/08");
  });

  it("a virada da meia-noite local separa ontem de hoje", () => {
    fixarFuso("America/Sao_Paulo");
    // 00:05 de 11/09 em Sao Paulo.
    agoraEm("2026-09-11T03:05:00Z");

    // 23:55 de 10/09 local: dez minutos antes, e ainda assim outro dia.
    expect(quando("2026-09-11T02:55:00")).toBe("10/09");
    // 00:01 de 11/09 local: mesmo dia.
    expect(quando("2026-09-11T03:01:00")).toBe("00:01");
  });
});

describe("entrada que nao e data", () => {
  it.each([
    ["texto solto", "bananas"],
    ["string vazia", ""],
    ["so espaco", " "],
    ["data impossivel", "2026-13-45T99:99:99"],
  ])("%s vira celula vazia, nunca 'Invalid Date'", (_caso, entrada) => {
    fixarFuso("America/Sao_Paulo");
    agoraEm("2026-09-10T20:00:00Z");

    expect(quando(entrada)).toBe("");
  });
});
