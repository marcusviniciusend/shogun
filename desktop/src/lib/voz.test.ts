/**
 * Testes da selecao de voz e do disparo do TTS.
 *
 * Ouvir continua sendo humano — nenhum agente tem alto-falante, e o bloco F8
 * do roteiro nasceu 100% manual por isso. O que da para prender aqui e tudo o
 * que acontece ANTES do som sair: qual voz foi escolhida, com que `lang` o
 * utterance foi montado, e se a fala anterior foi cancelada antes da nova.
 *
 * O `speechSynthesis` e do WebView2 e nao existe no ambiente de teste, entao
 * `window` e o construtor de utterance sao dublados. O modulo guarda a voz
 * escolhida em estado de modulo — dai o `vi.resetModules()` por teste.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

/** Voz dublada — so `lang` e `name` importam para a escolha. */
function voz(lang: string, name = lang): SpeechSynthesisVoice {
  return { lang, name } as SpeechSynthesisVoice;
}

interface Sintese {
  getVoices: ReturnType<typeof vi.fn>;
  addEventListener: ReturnType<typeof vi.fn>;
  cancel: ReturnType<typeof vi.fn>;
  speak: ReturnType<typeof vi.fn>;
}

/** Instala o `window.speechSynthesis` dublado e devolve os espioes. */
function instalarSintese(vozes: SpeechSynthesisVoice[] = []): Sintese {
  const sintese: Sintese = {
    getVoices: vi.fn(() => vozes),
    addEventListener: vi.fn(),
    cancel: vi.fn(),
    speak: vi.fn(),
  };
  vi.stubGlobal("window", { speechSynthesis: sintese });
  vi.stubGlobal(
    "SpeechSynthesisUtterance",
    class {
      lang = "";
      voice: SpeechSynthesisVoice | null = null;
      constructor(public text: string) {}
    },
  );
  return sintese;
}

/** Recarrega o modulo: a voz escolhida vive em estado de modulo. */
async function carregarModulo() {
  vi.resetModules();
  return await import("./voz");
}

/** O utterance que chegou ao `speak` — e onde `lang` e `voice` se conferem. */
function falaDe(sintese: Sintese): SpeechSynthesisUtterance {
  expect(sintese.speak).toHaveBeenCalledTimes(1);
  return sintese.speak.mock.calls[0][0];
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

describe("escolha de voz pt-BR (F8.1)", () => {
  it("prefere pt-BR mesmo com outras vozes na frente", async () => {
    const ptBr = voz("pt-BR", "Maria");
    const sintese = instalarSintese([
      voz("en-US", "Zira"),
      voz("pt-PT", "Joana"),
      ptBr,
    ]);
    const { inicializarVozes, falar } = await carregarModulo();

    inicializarVozes();
    falar("bom dia");

    expect(falaDe(sintese).voice).toBe(ptBr);
  });

  it.each(["pt_BR", "PT-BR", "pt-br"])(
    "reconhece a variante de escrita %s",
    async (lang) => {
      const alvo = voz(lang);
      const sintese = instalarSintese([voz("en-US"), alvo]);
      const { inicializarVozes, falar } = await carregarModulo();

      inicializarVozes();
      falar("bom dia");

      expect(falaDe(sintese).voice).toBe(alvo);
    },
  );

  it("sem pt-BR, cai em qualquer pt antes de desistir", async () => {
    const ptPt = voz("pt-PT", "Joana");
    const sintese = instalarSintese([voz("en-US"), ptPt, voz("es-ES")]);
    const { inicializarVozes, falar } = await carregarModulo();

    inicializarVozes();
    falar("bom dia");

    expect(falaDe(sintese).voice).toBe(ptPt);
  });

  it("sem nenhuma voz pt, sai na voz default do sistema — fallback, nao erro", async () => {
    const sintese = instalarSintese([voz("en-US"), voz("es-ES")]);
    const { inicializarVozes, falar } = await carregarModulo();

    inicializarVozes();
    falar("bom dia");

    const fala = falaDe(sintese);
    expect(fala.voice).toBeNull();
    // `lang` continua pt-BR: o motor tenta a pronuncia certa com o que tiver.
    expect(fala.lang).toBe("pt-BR");
  });

  it("lista vazia na montagem: a voz chega no voiceschanged e e adotada", async () => {
    // No WebView2 `getVoices()` costuma devolver vazio ate o motor carregar —
    // e o caso que mais quebra na pratica.
    const sintese = instalarSintese([]);
    const { inicializarVozes, falar } = await carregarModulo();

    inicializarVozes();
    expect(sintese.addEventListener).toHaveBeenCalledWith(
      "voiceschanged",
      expect.any(Function),
    );

    const ptBr = voz("pt-BR", "Maria");
    sintese.getVoices.mockReturnValue([voz("en-US"), ptBr]);
    sintese.addEventListener.mock.calls[0][1]();

    falar("bom dia");

    expect(falaDe(sintese).voice).toBe(ptBr);
  });

  it("perder a voz pt depois volta para a default, sem guardar voz morta", async () => {
    const sintese = instalarSintese([voz("pt-BR", "Maria")]);
    const { inicializarVozes, falar } = await carregarModulo();

    inicializarVozes();
    sintese.getVoices.mockReturnValue([voz("en-US")]);
    sintese.addEventListener.mock.calls[0][1]();

    falar("bom dia");

    expect(falaDe(sintese).voice).toBeNull();
  });

  it("sem inicializar, fala mesmo assim na voz default", async () => {
    const sintese = instalarSintese([voz("pt-BR")]);
    const { falar } = await carregarModulo();

    falar("bom dia");

    expect(falaDe(sintese).voice).toBeNull();
    expect(falaDe(sintese).lang).toBe("pt-BR");
  });
});

describe("falar (F8.6)", () => {
  it("fala o texto recebido, sem alterar", async () => {
    const sintese = instalarSintese([]);
    const { falar } = await carregarModulo();

    falar("Pedi para este aparelho abrir o Spotify, Marcus.");

    expect(falaDe(sintese).text).toBe(
      "Pedi para este aparelho abrir o Spotify, Marcus.",
    );
  });

  it("cancela a fala anterior ANTES de falar a nova", async () => {
    const sintese = instalarSintese([]);
    const { falar } = await carregarModulo();

    falar("primeira");
    falar("segunda");

    expect(sintese.cancel).toHaveBeenCalledTimes(2);
    expect(sintese.speak).toHaveBeenCalledTimes(2);
    // A ordem e o que impede duas vozes sobrepostas: resposta nova cala a
    // antiga, nada de fila.
    const ordemCancel = sintese.cancel.mock.invocationCallOrder[1];
    const ordemSpeak = sintese.speak.mock.invocationCallOrder[1];
    expect(ordemCancel).toBeLessThan(ordemSpeak);
  });

  it.each([
    ["vazio", ""],
    ["so espacos", "   "],
    ["so quebra de linha", "\n\t"],
  ])("texto %s nao fala nem cancela a fala em curso", async (_caso, texto) => {
    const sintese = instalarSintese([]);
    const { falar } = await carregarModulo();

    falar(texto);

    expect(sintese.speak).not.toHaveBeenCalled();
    // Nao cancelar importa: um texto vazio no meio do caminho calaria uma
    // resposta boa que ainda esta sendo falada.
    expect(sintese.cancel).not.toHaveBeenCalled();
  });
});

describe("calar (F8.7)", () => {
  it("interrompe a fala em curso", async () => {
    const sintese = instalarSintese([]);
    const { calar } = await carregarModulo();

    calar();

    expect(sintese.cancel).toHaveBeenCalledTimes(1);
  });

  it("e idempotente — chamar sem nada falando nao quebra", async () => {
    const sintese = instalarSintese([]);
    const { calar } = await carregarModulo();

    calar();
    calar();

    expect(sintese.cancel).toHaveBeenCalledTimes(2);
  });
});

describe("ambiente sem speechSynthesis (webview antigo)", () => {
  it("nenhuma das tres funcoes levanta erro", async () => {
    vi.stubGlobal("window", {});
    const { inicializarVozes, falar, calar } = await carregarModulo();

    expect(() => inicializarVozes()).not.toThrow();
    expect(() => falar("bom dia")).not.toThrow();
    expect(() => calar()).not.toThrow();
  });

  it("sem window nenhuma tambem nao quebra", async () => {
    vi.stubGlobal("window", undefined);
    const { inicializarVozes, falar, calar } = await carregarModulo();

    expect(() => inicializarVozes()).not.toThrow();
    expect(() => falar("bom dia")).not.toThrow();
    expect(() => calar()).not.toThrow();
  });
});
