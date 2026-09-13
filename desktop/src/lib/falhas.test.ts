/**
 * Testes do roteamento de falhas e da politica de reenvio da fiacao.
 *
 * Cobre as decisoes que os blocos F1 (banner de conexao), F3 (erro por tipo)
 * e F4 (429) do roteiro de regressao exercitavam a mao: qual falha vai para
 * o banner do topo e qual fica na bolha; quando ha o UNICO reenvio
 * automatico (so 503); e por quanto tempo o refresh do painel pausa depois
 * de um rate limit.
 *
 * `falhas.ts` importa `ErroComando` de `api.ts`, que importa o fetch do
 * tauri-plugin-http — dublado aqui como nos demais testes, embora nenhum
 * caso toque a rede.
 */
import { describe, expect, it, vi } from "vitest";

vi.mock("@tauri-apps/plugin-http", () => ({ fetch: vi.fn() }));

import { ErroComando, type TipoErro } from "./api";
import {
  ESPERA_REENVIO_MS,
  comReenvioUnico,
  deveReenviar,
  mensagemDeErro,
  mensagemServidorFora,
  pausaAposRateLimit,
  refreshSuspenso,
  rotearFalha,
} from "./falhas";

/** ErroComando minimo de um tipo dado, com mensagem que o identifica. */
function erro(tipo: TipoErro, retryAfterSegundos?: number): ErroComando {
  return new ErroComando(`falha de ${tipo}`, tipo, undefined, retryAfterSegundos);
}

const TIPOS_LOCAIS: TipoErro[] = [
  "auth",
  "llm_indisponivel",
  "rate_limit",
  "http",
  "formato",
];

describe("mensagemDeErro", () => {
  it("ErroComando mostra a propria mensagem, ja traduzida", () => {
    expect(mensagemDeErro(erro("auth"))).toBe("falha de auth");
  });

  it.each([
    ["Error comum", new Error("stack trace interna")],
    ["string solta", "boom"],
    ["undefined", undefined],
  ])("%s cai na frase generica, sem vazar detalhe interno", (_caso, e) => {
    expect(mensagemDeErro(e)).toBe("Erro inesperado ao falar com o servidor.");
  });
});

describe("rotearFalha — banner do topo x texto local", () => {
  it.each(["rede", "timeout"] as TipoErro[])(
    "%s vai para o banner e o local recebe so a frase que aponta para la",
    (tipo) => {
      const rota = rotearFalha(erro(tipo));

      expect(rota.motivoBanner).toBe(`falha de ${tipo}`);
      expect(rota.textoLocal).toBe(mensagemServidorFora());
    },
  );

  it("a frase local aponta para o topo — o detalhe mora em um lugar so", () => {
    expect(mensagemServidorFora()).toContain("no topo");
  });

  it.each(TIPOS_LOCAIS)("%s fica onde ocorreu, sem tocar o banner", (tipo) => {
    const rota = rotearFalha(erro(tipo));

    expect(rota.motivoBanner).toBeNull();
    expect(rota.textoLocal).toBe(`falha de ${tipo}`);
  });

  it("falha que nao e ErroComando fica local, com a frase generica", () => {
    const rota = rotearFalha(new Error("boom"));

    expect(rota.motivoBanner).toBeNull();
    expect(rota.textoLocal).toBe("Erro inesperado ao falar com o servidor.");
  });
});

describe("deveReenviar — so o 503 ganha nova tentativa", () => {
  it("llm_indisponivel reenvia", () => {
    expect(deveReenviar(erro("llm_indisponivel"))).toBe(true);
  });

  it.each(["rede", "timeout", "auth", "rate_limit", "http", "formato"] as TipoErro[])(
    "%s NAO reenvia",
    (tipo) => {
      expect(deveReenviar(erro(tipo))).toBe(false);
    },
  );

  it("falha que nao e ErroComando NAO reenvia", () => {
    expect(deveReenviar(new Error("boom"))).toBe(false);
  });
});

describe("comReenvioUnico — o sequenciamento do reenvio", () => {
  it("sucesso de primeira nao espera nem reenvia", async () => {
    const enviar = vi.fn().mockResolvedValue("ok");
    const esperar = vi.fn().mockResolvedValue(undefined);

    await expect(comReenvioUnico(enviar, esperar)).resolves.toBe("ok");
    expect(enviar).toHaveBeenCalledTimes(1);
    expect(esperar).not.toHaveBeenCalled();
  });

  it("503 na primeira: espera e a segunda tentativa responde", async () => {
    const ordem: string[] = [];
    const enviar = vi
      .fn()
      .mockImplementationOnce(() => {
        ordem.push("envio1");
        return Promise.reject(erro("llm_indisponivel"));
      })
      .mockImplementationOnce(() => {
        ordem.push("envio2");
        return Promise.resolve("ok");
      });
    const esperar = vi.fn().mockImplementation(() => {
      ordem.push("espera");
      return Promise.resolve();
    });

    await expect(comReenvioUnico(enviar, esperar)).resolves.toBe("ok");
    // A espera fica ENTRE as tentativas — e o tempo de o modelo local carregar.
    expect(ordem).toEqual(["envio1", "espera", "envio2"]);
  });

  it("503 duas vezes: o segundo erro propaga — reenvio e UM so", async () => {
    const segundo = erro("llm_indisponivel");
    const enviar = vi
      .fn()
      .mockRejectedValueOnce(erro("llm_indisponivel"))
      .mockRejectedValueOnce(segundo);
    const esperar = vi.fn().mockResolvedValue(undefined);

    await expect(comReenvioUnico(enviar, esperar)).rejects.toBe(segundo);
    expect(enviar).toHaveBeenCalledTimes(2);
    expect(esperar).toHaveBeenCalledTimes(1);
  });

  it.each(["auth", "rede", "rate_limit"] as TipoErro[])(
    "%s propaga imediato, sem espera e sem segunda tentativa",
    async (tipo) => {
      const falha = erro(tipo);
      const enviar = vi.fn().mockRejectedValue(falha);
      const esperar = vi.fn().mockResolvedValue(undefined);

      await expect(comReenvioUnico(enviar, esperar)).rejects.toBe(falha);
      expect(enviar).toHaveBeenCalledTimes(1);
      expect(esperar).not.toHaveBeenCalled();
    },
  );

  it("erro que nao e ErroComando tambem propaga sem reenvio", async () => {
    const falha = new Error("boom");
    const enviar = vi.fn().mockRejectedValue(falha);
    const esperar = vi.fn().mockResolvedValue(undefined);

    await expect(comReenvioUnico(enviar, esperar)).rejects.toBe(falha);
    expect(enviar).toHaveBeenCalledTimes(1);
    expect(esperar).not.toHaveBeenCalled();
  });

  it("a espera do App e curta o bastante para nao parecer travamento", () => {
    // 2s: da tempo de o modelo local subir sem segurar o "Pensando..." demais.
    expect(ESPERA_REENVIO_MS).toBe(2000);
  });
});

describe("pausaAposRateLimit — quanto tempo o refresh automatico dorme", () => {
  const AGORA = 1_000_000;
  const CICLO_MS = 30_000;

  it("honra o Retry-After que o servidor mandou", () => {
    expect(pausaAposRateLimit(erro("rate_limit", 7), AGORA, CICLO_MS)).toBe(
      AGORA + 7_000,
    );
  });

  it("sem Retry-After, pausa um ciclo inteiro", () => {
    expect(pausaAposRateLimit(erro("rate_limit"), AGORA, CICLO_MS)).toBe(
      AGORA + CICLO_MS,
    );
  });

  it("Retry-After zero nao vira pausa de um ciclo — zero e zero", () => {
    expect(pausaAposRateLimit(erro("rate_limit", 0), AGORA, CICLO_MS)).toBe(
      AGORA,
    );
  });

  it.each(["rede", "timeout", "auth", "llm_indisponivel", "http", "formato"] as TipoErro[])(
    "%s nao cria pausa nova",
    (tipo) => {
      expect(pausaAposRateLimit(erro(tipo), AGORA, CICLO_MS)).toBeNull();
    },
  );

  it("falha que nao e ErroComando nao cria pausa", () => {
    expect(pausaAposRateLimit(new Error("boom"), AGORA, CICLO_MS)).toBeNull();
  });
});

describe("refreshSuspenso — o tick respeita a pausa", () => {
  it("sem pausa registrada, o tick roda", () => {
    expect(refreshSuspenso(null, 1_000)).toBe(false);
  });

  it("antes do fim da pausa, o tick e suprimido", () => {
    expect(refreshSuspenso(2_000, 1_999)).toBe(true);
  });

  it("no instante exato do fim, o tick volta", () => {
    expect(refreshSuspenso(2_000, 2_000)).toBe(false);
  });

  it("depois do fim, o tick volta", () => {
    expect(refreshSuspenso(2_000, 3_000)).toBe(false);
  });
});
