/**
 * Testes do fluxo de ditado (push-to-talk).
 *
 * O transcritor aqui e SEMPRE mockado — o motor real (`lib/stt.ts`) e de
 * outra branch, e a costura entre as duas e exatamente a assinatura
 * `Transcritor` exercitada nestes testes. Com captura e transcritor dublados,
 * o ciclo inteiro (segurar → gravar → soltar → transcrever → texto no fluxo
 * de envio) roda no vitest; o que sobra de manual esta no bloco F9 do
 * roteiro.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  criarControleDitado,
  mensagemErroCaptura,
  podeGravar,
  rotuloBotao,
  statusDitado,
  textoUtil,
  transcritorDeDesenvolvimento,
  type EstadoDitado,
} from "./ditado";
import { CapturaIndisponivelError, type Captura } from "./microfone";

/* ------------------------------------------------------------------ puras */

describe("podeGravar", () => {
  it("so grava do ocioso, com chat livre e servidor alcancavel", () => {
    expect(podeGravar("ocioso", false, false)).toBe(true);
    expect(podeGravar("gravando", false, false)).toBe(false);
    expect(podeGravar("transcrevendo", false, false)).toBe(false);
    expect(podeGravar("ocioso", true, false)).toBe(false);
    expect(podeGravar("ocioso", false, true)).toBe(false);
  });
});

describe("rotulos e status por estado", () => {
  it.each<[EstadoDitado, string]>([
    ["ocioso", "Segurar para falar"],
    ["gravando", "Gravando — solte para enviar"],
    ["transcrevendo", "Transcrevendo…"],
  ])("botao em %s: %s", (estado, rotulo) => {
    expect(rotuloBotao(estado)).toBe(rotulo);
  });

  it("status: ocioso fica em silencio, os outros explicam a fase", () => {
    expect(statusDitado("ocioso")).toBeNull();
    expect(statusDitado("gravando")).toBe("Ouvindo — solte para enviar.");
    expect(statusDitado("transcrevendo")).toBe("Transcrevendo…");
  });
});

describe("mensagemErroCaptura", () => {
  it("recusa de permissao aponta a chave de privacidade do Windows", () => {
    const recusa = Object.assign(new Error("x"), { name: "NotAllowedError" });
    expect(mensagemErroCaptura(recusa)).toContain("Privacidade e segurança");
    const seguranca = Object.assign(new Error("x"), { name: "SecurityError" });
    expect(mensagemErroCaptura(seguranca)).toContain("Microfone");
  });

  it("sem microfone e mic ocupado tem frases proprias", () => {
    const semMic = Object.assign(new Error("x"), { name: "NotFoundError" });
    expect(mensagemErroCaptura(semMic)).toBe("Nenhum microfone encontrado.");
    const ocupado = Object.assign(new Error("x"), { name: "NotReadableError" });
    expect(mensagemErroCaptura(ocupado)).toBe(
      "O microfone está em uso por outro aplicativo.",
    );
  });

  it("API ausente pede atualizacao do WebView2", () => {
    expect(mensagemErroCaptura(new CapturaIndisponivelError("teste"))).toContain(
      "WebView2",
    );
  });

  it("qualquer outra coisa cai na frase generica", () => {
    expect(mensagemErroCaptura(new Error("boom"))).toBe(
      "Não consegui acessar o microfone.",
    );
    expect(mensagemErroCaptura(undefined)).toBe(
      "Não consegui acessar o microfone.",
    );
  });
});

describe("textoUtil", () => {
  it("apara espacos e devolve null para vazio — nada de comando em branco", () => {
    expect(textoUtil("  abrir a calculadora  ")).toBe("abrir a calculadora");
    expect(textoUtil("")).toBeNull();
    expect(textoUtil("   \n\t")).toBeNull();
  });
});

/* ------------------------------------------------------------- controlador */

function capturaFalsa(pcm = new Float32Array([0.1, 0.2])) {
  return {
    parar: vi.fn(() => Promise.resolve(pcm)),
    cancelar: vi.fn(() => {}),
  };
}

function sinaisFalsos() {
  return {
    aoEstado: vi.fn((_estado: EstadoDitado) => {}),
    aoTexto: vi.fn((_texto: string) => {}),
    aoErro: vi.fn((_mensagem: string) => {}),
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  // O controlador loga a causa crua no console; os testes nao precisam dela.
  vi.spyOn(console, "error").mockImplementation(() => {});
});

describe("criarControleDitado — fluxo feliz", () => {
  it("cala o TTS ANTES de abrir o microfone, sempre", async () => {
    const calar = vi.fn();
    const iniciarCaptura = vi.fn(() => Promise.resolve(capturaFalsa()));
    const controle = criarControleDitado(
      { calar, iniciarCaptura, transcritor: vi.fn(async (_pcm: Float32Array) => "") },
      sinaisFalsos(),
    );

    await controle.iniciar();

    expect(calar).toHaveBeenCalledTimes(1);
    const ordemCalar = calar.mock.invocationCallOrder[0];
    const ordemCaptura = iniciarCaptura.mock.invocationCallOrder[0];
    expect(ordemCalar).toBeLessThan(ordemCaptura);
  });

  it("grava, transcreve e entrega o texto aparado ao fluxo de envio", async () => {
    const pcm = new Float32Array([0.5]);
    const captura = capturaFalsa(pcm);
    const transcritor = vi.fn(() => Promise.resolve("  abrir o spotify  "));
    const sinais = sinaisFalsos();
    const controle = criarControleDitado(
      { calar: vi.fn(), iniciarCaptura: async () => captura, transcritor },
      sinais,
    );

    await controle.iniciar();
    await controle.parar();

    // O transcritor recebeu EXATAMENTE o PCM que a captura entregou.
    expect(transcritor).toHaveBeenCalledWith(pcm);
    expect(sinais.aoTexto).toHaveBeenCalledWith("abrir o spotify");
    expect(sinais.aoErro).not.toHaveBeenCalled();
    // Estados na ordem do desenho: gravando → transcrevendo → ocioso.
    expect(sinais.aoEstado.mock.calls.map((c) => c[0])).toEqual([
      "gravando",
      "transcrevendo",
      "ocioso",
    ]);
  });

  it("transcricao vazia nao envia nada e volta ao ocioso", async () => {
    const sinais = sinaisFalsos();
    const controle = criarControleDitado(
      {
        calar: vi.fn(),
        iniciarCaptura: async () => capturaFalsa(),
        transcritor: async () => "   ",
      },
      sinais,
    );

    await controle.iniciar();
    await controle.parar();

    expect(sinais.aoTexto).not.toHaveBeenCalled();
    expect(sinais.aoErro).not.toHaveBeenCalled();
    expect(sinais.aoEstado).toHaveBeenLastCalledWith("ocioso");
  });
});

describe("criarControleDitado — falhas", () => {
  it("recusa do microfone vira mensagem local e o estado nem sai do ocioso", async () => {
    const sinais = sinaisFalsos();
    const recusa = Object.assign(new Error("x"), { name: "NotAllowedError" });
    const controle = criarControleDitado(
      {
        calar: vi.fn(),
        iniciarCaptura: () => Promise.reject(recusa),
        transcritor: vi.fn(async (_pcm: Float32Array) => ""),
      },
      sinais,
    );

    await controle.iniciar();

    expect(sinais.aoErro).toHaveBeenCalledWith(
      expect.stringContaining("Privacidade"),
    );
    expect(sinais.aoEstado).not.toHaveBeenCalled();
    // A causa crua foi para o console, prefixada — e o que o roteiro manda olhar.
    expect(console.error).toHaveBeenCalledWith(
      expect.stringContaining("[shogun]"),
      recusa,
    );
  });

  it("falha do transcritor vira erro local e volta ao ocioso", async () => {
    const sinais = sinaisFalsos();
    const controle = criarControleDitado(
      {
        calar: vi.fn(),
        iniciarCaptura: async () => capturaFalsa(),
        transcritor: () => Promise.reject(new Error("motor caiu")),
      },
      sinais,
    );

    await controle.iniciar();
    await controle.parar();

    expect(sinais.aoErro).toHaveBeenCalledWith(
      "Não consegui transcrever o áudio.",
    );
    expect(sinais.aoTexto).not.toHaveBeenCalled();
    expect(sinais.aoEstado).toHaveBeenLastCalledWith("ocioso");
  });

  it("falha do parar da captura tambem vira erro local, sem texto", async () => {
    const captura = capturaFalsa();
    captura.parar.mockRejectedValue(new Error("stream morreu"));
    const transcritor = vi.fn(async (_pcm: Float32Array) => "");
    const sinais = sinaisFalsos();
    const controle = criarControleDitado(
      { calar: vi.fn(), iniciarCaptura: async () => captura, transcritor },
      sinais,
    );

    await controle.iniciar();
    await controle.parar();

    expect(transcritor).not.toHaveBeenCalled();
    expect(sinais.aoErro).toHaveBeenCalledTimes(1);
    expect(sinais.aoEstado).toHaveBeenLastCalledWith("ocioso");
  });
});

describe("criarControleDitado — corridas do push-to-talk", () => {
  it("soltar ANTES de o mic abrir descarta a captura — toque rapido e desistencia", async () => {
    const captura = capturaFalsa();
    let abrir!: (c: Captura) => void;
    const pendente = new Promise<Captura>((resolve) => {
      abrir = resolve;
    });
    const transcritor = vi.fn(async (_pcm: Float32Array) => "");
    const sinais = sinaisFalsos();
    const controle = criarControleDitado(
      { calar: vi.fn(), iniciarCaptura: () => pendente, transcritor },
      sinais,
    );

    const iniciando = controle.iniciar();
    await controle.parar(); // soltou antes do getUserMedia resolver
    abrir(captura);
    await iniciando;

    expect(captura.cancelar).toHaveBeenCalledTimes(1);
    expect(transcritor).not.toHaveBeenCalled();
    expect(sinais.aoEstado).not.toHaveBeenCalledWith("gravando");
  });

  it("cancelar enquanto abre tambem descarta", async () => {
    const captura = capturaFalsa();
    let abrir!: (c: Captura) => void;
    const pendente = new Promise<Captura>((resolve) => {
      abrir = resolve;
    });
    const sinais = sinaisFalsos();
    const controle = criarControleDitado(
      { calar: vi.fn(), iniciarCaptura: () => pendente, transcritor: vi.fn(async (_pcm: Float32Array) => "") },
      sinais,
    );

    const iniciando = controle.iniciar();
    controle.cancelar();
    abrir(captura);
    await iniciando;

    expect(captura.cancelar).toHaveBeenCalledTimes(1);
    expect(sinais.aoEstado).not.toHaveBeenCalled();
  });

  it("cancelar durante a gravacao descarta sem transcrever", async () => {
    const captura = capturaFalsa();
    const transcritor = vi.fn(async (_pcm: Float32Array) => "");
    const sinais = sinaisFalsos();
    const controle = criarControleDitado(
      { calar: vi.fn(), iniciarCaptura: async () => captura, transcritor },
      sinais,
    );

    await controle.iniciar();
    controle.cancelar();

    expect(captura.cancelar).toHaveBeenCalledTimes(1);
    expect(captura.parar).not.toHaveBeenCalled();
    expect(transcritor).not.toHaveBeenCalled();
    expect(sinais.aoEstado).toHaveBeenLastCalledWith("ocioso");
  });

  it("iniciar de novo durante a gravacao e no-op — nao abre segundo mic", async () => {
    const iniciarCaptura = vi.fn(() => Promise.resolve(capturaFalsa()));
    const controle = criarControleDitado(
      { calar: vi.fn(), iniciarCaptura, transcritor: vi.fn(async (_pcm: Float32Array) => "") },
      sinaisFalsos(),
    );

    await controle.iniciar();
    await controle.iniciar();

    expect(iniciarCaptura).toHaveBeenCalledTimes(1);
  });

  it("parar sem estar gravando e no-op", async () => {
    const sinais = sinaisFalsos();
    const controle = criarControleDitado(
      {
        calar: vi.fn(),
        iniciarCaptura: async () => capturaFalsa(),
        transcritor: vi.fn(async (_pcm: Float32Array) => ""),
      },
      sinais,
    );

    await controle.parar();

    expect(sinais.aoEstado).not.toHaveBeenCalled();
    expect(sinais.aoErro).not.toHaveBeenCalled();
  });

  it("ciclo novo depois de um completo funciona — o controlador se rearma", async () => {
    const sinais = sinaisFalsos();
    const controle = criarControleDitado(
      {
        calar: vi.fn(),
        iniciarCaptura: async () => capturaFalsa(),
        transcritor: async () => "de novo",
      },
      sinais,
    );

    await controle.iniciar();
    await controle.parar();
    await controle.iniciar();
    await controle.parar();

    expect(sinais.aoTexto).toHaveBeenCalledTimes(2);
  });
});

describe("transcritorDeDesenvolvimento", () => {
  it("loga a captura com o prefixo [shogun] e devolve vazio — nada vai ao servidor", async () => {
    const info = vi.spyOn(console, "info").mockImplementation(() => {});
    const texto = await transcritorDeDesenvolvimento(
      new Float32Array([0.25, -0.5]),
    );
    expect(texto).toBe("");
    expect(info).toHaveBeenCalledWith(expect.stringContaining("[shogun]"));
  });
});
