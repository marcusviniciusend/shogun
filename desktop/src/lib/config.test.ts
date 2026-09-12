/**
 * Testes da configuracao persistida.
 *
 * O `tauri-plugin-store` so existe dentro do app, entao o roteiro de regressao
 * mandava abrir o `%APPDATA%\shogun.json` a olho (F5.4) e reabrir o app para
 * conferir preferencia guardada (F5.2, F8.5). Com o store dublado, o que se
 * verifica e o que o modulo PEDE ao store — chave gravada, chave apagada,
 * default aplicado — que e exatamente o que aquele arquivo refletiria.
 *
 * Cada teste recarrega o modulo (`vi.resetModules`) de proposito: `config.ts`
 * guarda a promessa do store num modulo-nivel, e sem o reset um teste herdaria
 * o store do anterior.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

const { loadMock, get, set, deletar, dados } = vi.hoisted(() => {
  const dados = new Map<string, unknown>();
  return {
    dados,
    loadMock: vi.fn(),
    get: vi.fn(async (chave: string) => dados.get(chave)),
    set: vi.fn(async (chave: string, valor: unknown) => {
      dados.set(chave, valor);
    }),
    deletar: vi.fn(async (chave: string) => dados.delete(chave)),
  };
});

vi.mock("@tauri-apps/plugin-store", () => ({ load: loadMock }));

/** Recarrega o modulo com o store zerado — ver a nota do cabecalho. */
async function carregarModulo() {
  vi.resetModules();
  return await import("./config");
}

/** Raiz dublada: `dataset` e objeto simples, que aceita `delete` e atribuicao. */
function raizDublada(): { dataset: Record<string, string> } {
  const raiz = { dataset: {} as Record<string, string> };
  vi.stubGlobal("document", { documentElement: raiz });
  return raiz;
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.unstubAllGlobals();
  dados.clear();
  loadMock.mockResolvedValue({ get, set, delete: deletar });
});

describe("carregarConfig — defaults de primeiro uso", () => {
  it("store vazio devolve o default inteiro", async () => {
    const { carregarConfig, CONFIG_DEFAULT } = await carregarModulo();

    await expect(carregarConfig()).resolves.toEqual(CONFIG_DEFAULT);
  });

  it("o Shogun nasce FALANDO: mudo default e false", async () => {
    const { CONFIG_DEFAULT } = await carregarModulo();

    expect(CONFIG_DEFAULT.mudo).toBe(false);
    expect(CONFIG_DEFAULT.tema).toBe("washi");
    expect(CONFIG_DEFAULT.token).toBe("");
  });

  it("le de volta o que foi guardado", async () => {
    dados.set("serverUrl", "http://100.64.0.1:8000");
    dados.set("token", "segredo");
    dados.set("tema", "sumi");
    dados.set("mudo", true);
    const { carregarConfig } = await carregarModulo();

    await expect(carregarConfig()).resolves.toEqual({
      serverUrl: "http://100.64.0.1:8000",
      token: "segredo",
      tema: "sumi",
      mudo: true,
    });
  });

  it.each(["washi", "sumi", "sistema"] as const)(
    "tema %s e aceito como esta",
    async (tema) => {
      dados.set("tema", tema);
      const { carregarConfig } = await carregarModulo();

      expect((await carregarConfig()).tema).toBe(tema);
    },
  );

  it.each([
    ["valor de versao antiga", "escuro"],
    ["edicao manual errada", "SUMI"],
    ["tipo errado", 42],
    ["vazio", ""],
  ])("tema invalido (%s) cai no default em vez de virar data-tema desconhecido", async (
    _caso,
    invalido,
  ) => {
    dados.set("tema", invalido);
    const { carregarConfig } = await carregarModulo();

    expect((await carregarConfig()).tema).toBe("washi");
  });
});

describe("salvarConfig", () => {
  it("grava as quatro chaves do contrato", async () => {
    const { salvarConfig } = await carregarModulo();

    await salvarConfig({
      serverUrl: "http://localhost:8000",
      token: "segredo",
      tema: "sumi",
      mudo: true,
    });

    expect(dados.get("serverUrl")).toBe("http://localhost:8000");
    expect(dados.get("token")).toBe("segredo");
    expect(dados.get("tema")).toBe("sumi");
    expect(dados.get("mudo")).toBe(true);
  });

  it.each([
    ["http://localhost:8000/", "http://localhost:8000"],
    ["http://localhost:8000///", "http://localhost:8000"],
    ["http://localhost:8000", "http://localhost:8000"],
  ])(
    "tira a barra final de %s — as rotas ja trazem a sua",
    async (digitado, gravado) => {
      const { salvarConfig, CONFIG_DEFAULT } = await carregarModulo();

      await salvarConfig({ ...CONFIG_DEFAULT, serverUrl: digitado });

      // Com a barra sobrando o cliente pediria //comando, e o servidor
      // responderia 404 — falha que parece "servidor errado".
      expect(dados.get("serverUrl")).toBe(gravado);
    },
  );

  it("o que salvarConfig grava, carregarConfig le de volta igual", async () => {
    const { salvarConfig, carregarConfig } = await carregarModulo();
    const config = {
      serverUrl: "http://100.64.0.1:8000",
      token: "segredo",
      tema: "sistema" as const,
      mudo: true,
    };

    await salvarConfig(config);

    // F8.5 / F5.2: a preferencia sobrevive a reabertura do app.
    await expect(carregarConfig()).resolves.toEqual(config);
  });
});

describe("sessionId persistido (F5.1, F5.2, F5.4)", () => {
  it("grava o id quando ha conversa em curso", async () => {
    const { salvarSessionId } = await carregarModulo();

    await salvarSessionId("sessao-1");

    expect(set).toHaveBeenCalledWith("sessionId", "sessao-1");
    expect(dados.get("sessionId")).toBe("sessao-1");
  });

  it("F5.4: nova conversa REMOVE a chave, nao grava string vazia", async () => {
    dados.set("sessionId", "sessao-1");
    const { salvarSessionId } = await carregarModulo();

    await salvarSessionId(null);

    expect(deletar).toHaveBeenCalledWith("sessionId");
    // A distincao importa: uma string vazia gravada voltaria de
    // `carregarSessionId` como "" — valor falsy, mas nao `null` — e o proximo
    // POST sairia com session_id "" em vez de nulo.
    expect(set).not.toHaveBeenCalledWith("sessionId", "");
    expect(set).not.toHaveBeenCalled();
    expect(dados.has("sessionId")).toBe(false);
  });

  it("depois de remover, carregarSessionId devolve null", async () => {
    dados.set("sessionId", "sessao-1");
    const { salvarSessionId, carregarSessionId } = await carregarModulo();

    await salvarSessionId(null);

    await expect(carregarSessionId()).resolves.toBeNull();
  });

  it("sem nada guardado, carregarSessionId devolve null (nao undefined)", async () => {
    const { carregarSessionId } = await carregarModulo();

    // `null` e o que o contrato do POST /comando espera para conversa nova;
    // `undefined` sumiria do JSON e o servidor veria campo ausente.
    await expect(carregarSessionId()).resolves.toBeNull();
  });

  it("id guardado sobrevive ao fechamento do app", async () => {
    const { salvarSessionId } = await carregarModulo();
    await salvarSessionId("sessao-1");

    // Reabrir o app = modulo recarregado, store com o mesmo conteudo.
    const { carregarSessionId } = await carregarModulo();

    await expect(carregarSessionId()).resolves.toBe("sessao-1");
  });
});

describe("aplicarTema", () => {
  it("washi nao escreve atributo — e o que o :root ja define", async () => {
    const raiz = raizDublada();
    raiz.dataset.tema = "sumi";
    const { aplicarTema } = await carregarModulo();

    aplicarTema("washi");

    expect(raiz.dataset.tema).toBeUndefined();
  });

  it.each(["sumi", "sistema"] as const)("%s vira data-tema", async (tema) => {
    const raiz = raizDublada();
    const { aplicarTema } = await carregarModulo();

    aplicarTema(tema);

    expect(raiz.dataset.tema).toBe(tema);
  });
});

describe("temaEfetivo — escolha de asset por tema", () => {
  it.each(["washi", "sumi"] as const)("%s nao consulta o sistema", async (tema) => {
    const matchMedia = vi.fn();
    vi.stubGlobal("window", { matchMedia });
    const { temaEfetivo } = await carregarModulo();

    expect(temaEfetivo(tema)).toBe(tema);
    expect(matchMedia).not.toHaveBeenCalled();
  });

  it.each([
    [true, "sumi"],
    [false, "washi"],
  ])(
    "sistema com prefers-color-scheme: dark = %s vira %s",
    async (escuro, esperado) => {
      vi.stubGlobal("window", {
        matchMedia: vi.fn(() => ({ matches: escuro })),
      });
      const { temaEfetivo } = await carregarModulo();

      expect(temaEfetivo("sistema")).toBe(esperado);
    },
  );
});

describe("preCarregarTema — tema antes do primeiro paint", () => {
  it("aplica e devolve o tema guardado", async () => {
    dados.set("tema", "sumi");
    const raiz = raizDublada();
    const { preCarregarTema } = await carregarModulo();

    await expect(preCarregarTema()).resolves.toBe("sumi");
    expect(raiz.dataset.tema).toBe("sumi");
  });

  it("store inacessivel abre no default sem travar a inicializacao", async () => {
    loadMock.mockRejectedValue(new Error("store corrompido"));
    raizDublada();
    const { preCarregarTema } = await carregarModulo();

    await expect(preCarregarTema()).resolves.toBe("washi");
  });
});
