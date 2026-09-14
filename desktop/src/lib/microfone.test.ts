/**
 * Testes da captura de microfone.
 *
 * Como no TTS (`voz.test.ts`), o som de verdade continua humano: prompt de
 * permissao do WebView2, microfone fisico e qualidade do audio ficam no bloco
 * F9 do roteiro manual. O que se prende aqui e tudo que acontece com os
 * NUMEROS — media de canais, concatenacao, reamostragem (arrays sinteticos) —
 * e a fiacao do `iniciarCaptura` sobre globais dubladas: quais constraints
 * foram pedidas, se trilha e contexto fecham, se o PCM final sai em 16 kHz.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  CapturaIndisponivelError,
  TAXA_ALVO,
  concatenarBlocos,
  duracaoSegundos,
  iniciarCaptura,
  mediaCanais,
  picoAbsoluto,
  reamostrar,
} from "./microfone";

/* ------------------------------------------------------------------ puras */

describe("mediaCanais", () => {
  it("sem canal nenhum devolve vazio", () => {
    expect(mediaCanais([]).length).toBe(0);
  });

  it("um canal so passa direto — mas como copia, nao como referencia", () => {
    const canal = new Float32Array([0.1, -0.2, 0.3]);
    const saida = mediaCanais([canal]);
    expect(Array.from(saida)).toEqual(Array.from(canal));
    expect(saida).not.toBe(canal);
  });

  it("dois canais viram a media amostra a amostra", () => {
    const esquerdo = new Float32Array([1, 0, -1]);
    const direito = new Float32Array([0, 1, -1]);
    expect(Array.from(mediaCanais([esquerdo, direito]))).toEqual([
      0.5, 0.5, -1,
    ]);
  });

  it("canal mais curto conta como silencio, nao como NaN", () => {
    const cheio = new Float32Array([1, 1]);
    const curto = new Float32Array([1]);
    expect(Array.from(mediaCanais([cheio, curto]))).toEqual([1, 0.5]);
  });
});

describe("concatenarBlocos", () => {
  it("sem blocos devolve vazio", () => {
    expect(concatenarBlocos([]).length).toBe(0);
  });

  it("preserva ordem e conteudo dos blocos", () => {
    const saida = concatenarBlocos([
      new Float32Array([1, 2]),
      new Float32Array([]),
      new Float32Array([3]),
    ]);
    expect(Array.from(saida)).toEqual([1, 2, 3]);
  });
});

describe("reamostrar", () => {
  it("taxas iguais devolvem copia, nunca a mesma referencia", () => {
    const pcm = new Float32Array([0.1, 0.2]);
    const saida = reamostrar(pcm, TAXA_ALVO, TAXA_ALVO);
    expect(Array.from(saida)).toEqual(Array.from(pcm));
    expect(saida).not.toBe(pcm);
  });

  it("vazio continua vazio em qualquer taxa", () => {
    expect(reamostrar(new Float32Array(0), 48_000).length).toBe(0);
  });

  it("razao inteira decima por media de blocos (48 kHz -> 16 kHz)", () => {
    // razao 3: cada trio vira sua media — o passa-baixa rudimentar.
    const pcm = new Float32Array([0, 3, 3, 6, 6, 6]);
    expect(Array.from(reamostrar(pcm, 48_000, 16_000))).toEqual([2, 6]);
  });

  it("descarta o resto que nao fecha um bloco inteiro", () => {
    const pcm = new Float32Array([3, 3, 3, 9]); // razao 3: sobra 1 amostra
    expect(Array.from(reamostrar(pcm, 48_000, 16_000))).toEqual([3]);
  });

  it("um segundo a 48 kHz vira um segundo a 16 kHz", () => {
    const saida = reamostrar(new Float32Array(48_000), 48_000);
    expect(saida.length).toBe(TAXA_ALVO);
  });

  it("razao fracionaria interpola sem inventar amplitude (44,1 kHz)", () => {
    const constante = new Float32Array(4410).fill(0.5);
    const saida = reamostrar(constante, 44_100, 16_000);
    expect(saida.length).toBe(Math.floor(4410 / (44_100 / 16_000)));
    for (const amostra of saida) expect(amostra).toBeCloseTo(0.5, 6);
  });

  it("taxa de origem MENOR interpola para cima sem quebrar", () => {
    // 8 kHz -> 16 kHz: posicoes 0, 0.5, 1, 1.5 sobre [0, 1].
    const saida = reamostrar(new Float32Array([0, 1]), 8_000, 16_000);
    expect(Array.from(saida)).toEqual([0, 0.5, 1, 1]);
  });
});

describe("duracaoSegundos e picoAbsoluto", () => {
  it("32000 amostras a 16 kHz sao 2 segundos", () => {
    expect(duracaoSegundos(new Float32Array(32_000))).toBe(2);
  });

  it("pico e a maior amplitude em modulo; silencio da zero", () => {
    expect(picoAbsoluto(new Float32Array([0.1, -0.8, 0.3]))).toBeCloseTo(0.8);
    expect(picoAbsoluto(new Float32Array(4))).toBe(0);
  });
});

/* ----------------------------------------------------------------- fiacao */

/**
 * Instala getUserMedia + AudioContext + AudioWorkletNode dublados. A taxa que
 * o contexto "aceita" vem em `taxaDoContexto`; `recusa16k` simula dispositivo
 * que rejeita o construtor com `sampleRate` pedido.
 */
function instalarAudio({
  taxaDoContexto = TAXA_ALVO,
  recusa16k = false,
  semWorklet = false,
}: {
  taxaDoContexto?: number;
  recusa16k?: boolean;
  semWorklet?: boolean;
} = {}) {
  const pararTrilha = vi.fn(() => {});
  const fechar = vi.fn(() => Promise.resolve());
  const desconectar = vi.fn(() => {});
  const opcoesContexto: Array<AudioContextOptions | undefined> = [];
  const nos: Array<{ port: { onmessage: ((e: MessageEvent) => void) | null } }> =
    [];

  const stream = { getTracks: () => [{ stop: pararTrilha }] };
  const getUserMedia = vi.fn((_c: MediaStreamConstraints) =>
    Promise.resolve(stream),
  );
  vi.stubGlobal("navigator", { mediaDevices: { getUserMedia } });

  class ContextoFalso {
    sampleRate: number;
    audioWorklet = semWorklet
      ? undefined
      : { addModule: vi.fn(() => Promise.resolve()) };
    constructor(opcoes?: AudioContextOptions) {
      opcoesContexto.push(opcoes);
      if (recusa16k && opcoes?.sampleRate !== undefined) {
        throw new DOMException("taxa nao suportada", "NotSupportedError");
      }
      this.sampleRate = taxaDoContexto;
    }
    createMediaStreamSource() {
      return { connect: vi.fn(), disconnect: desconectar };
    }
    close() {
      return fechar();
    }
  }

  class NoFalso {
    port: { onmessage: ((e: MessageEvent) => void) | null } = {
      onmessage: null,
    };
    constructor() {
      nos.push(this);
    }
  }

  vi.stubGlobal("AudioContext", ContextoFalso);
  vi.stubGlobal("AudioWorkletNode", NoFalso);
  vi.stubGlobal("URL", {
    createObjectURL: vi.fn(() => "blob:falso"),
    revokeObjectURL: vi.fn(),
  });
  vi.stubGlobal("Blob", class {});
  return { getUserMedia, pararTrilha, fechar, desconectar, opcoesContexto, nos };
}

type Dubles = ReturnType<typeof instalarAudio>;

/** Entrega um quadro do worklet ao no criado. */
function chegarQuadro(dubles: Dubles, canais: Float32Array[]): void {
  const no = dubles.nos[0];
  expect(no.port.onmessage).toBeTypeOf("function");
  no.port.onmessage!({ data: canais } as MessageEvent);
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

describe("iniciarCaptura", () => {
  it("pede o pipeline de voz do Chromium nas constraints", async () => {
    const dubles = instalarAudio();
    await iniciarCaptura();
    expect(dubles.getUserMedia).toHaveBeenCalledWith({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
  });

  it("pede o contexto ja em 16 kHz", async () => {
    const dubles = instalarAudio();
    await iniciarCaptura();
    expect(dubles.opcoesContexto[0]).toEqual({ sampleRate: TAXA_ALVO });
  });

  it("dispositivo recusando 16 kHz cai no contexto default", async () => {
    const dubles = instalarAudio({ recusa16k: true, taxaDoContexto: 48_000 });
    await iniciarCaptura();
    // primeiro tentou com sampleRate, depois sem nada
    expect(dubles.opcoesContexto).toEqual([
      { sampleRate: TAXA_ALVO },
      undefined,
    ]);
  });

  it("acumula quadros e entrega PCM reamostrado para 16 kHz no parar", async () => {
    // Contexto a 32 kHz: razao 2, cada par de amostras vira sua media.
    const dubles = instalarAudio({ taxaDoContexto: 32_000 });
    const captura = await iniciarCaptura();

    chegarQuadro(dubles, [new Float32Array([0, 2])]);
    chegarQuadro(dubles, [new Float32Array([4, 6])]);

    const pcm = await captura.parar();
    expect(Array.from(pcm)).toEqual([1, 5]);
  });

  it("quadro estereo vira mono pela media antes de acumular", async () => {
    const dubles = instalarAudio();
    const captura = await iniciarCaptura();

    chegarQuadro(dubles, [new Float32Array([1, 0]), new Float32Array([0, 1])]);

    const pcm = await captura.parar();
    expect(Array.from(pcm)).toEqual([0.5, 0.5]);
  });

  it("parar fecha trilha e contexto", async () => {
    const dubles = instalarAudio();
    const captura = await iniciarCaptura();
    await captura.parar();
    expect(dubles.pararTrilha).toHaveBeenCalledTimes(1);
    expect(dubles.fechar).toHaveBeenCalledTimes(1);
  });

  it("cancelar descarta e fecha; repetir nao fecha duas vezes", async () => {
    const dubles = instalarAudio();
    const captura = await iniciarCaptura();
    captura.cancelar();
    captura.cancelar();
    expect(dubles.pararTrilha).toHaveBeenCalledTimes(1);
    expect(dubles.fechar).toHaveBeenCalledTimes(1);
  });

  it("sem getUserMedia lanca CapturaIndisponivelError", async () => {
    vi.stubGlobal("navigator", {});
    await expect(iniciarCaptura()).rejects.toBeInstanceOf(
      CapturaIndisponivelError,
    );
  });

  it("sem AudioWorklet lanca CapturaIndisponivelError e NAO deixa o mic aberto", async () => {
    const dubles = instalarAudio({ semWorklet: true });
    await expect(iniciarCaptura()).rejects.toBeInstanceOf(
      CapturaIndisponivelError,
    );
    // A trilha aberta pelo getUserMedia foi parada mesmo com a falha depois.
    expect(dubles.pararTrilha).toHaveBeenCalledTimes(1);
  });

  it("recusa de permissao propaga o erro original e para nada duas vezes", async () => {
    const dubles = instalarAudio();
    const recusa = Object.assign(new Error("negado"), {
      name: "NotAllowedError",
    });
    dubles.getUserMedia.mockRejectedValue(recusa);
    await expect(iniciarCaptura()).rejects.toBe(recusa);
    expect(dubles.pararTrilha).not.toHaveBeenCalled();
  });
});
