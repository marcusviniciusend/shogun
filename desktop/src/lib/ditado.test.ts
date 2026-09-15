/**
 * Testes do fluxo de ditado (clique alterna: clique abre, clique fecha).
 *
 * As dependencias continuam injetadas — agora sao os comandos Tauri de
 * `lib/stt.ts` (abrir microfone, parar e transcrever, cancelar) em vez do
 * objeto `Captura` que o extinto `lib/microfone.ts` entregava. E o que mantem
 * estes testes sem mock de Tauri: o ciclo inteiro (clicar → gravar → clicar
 * → transcrever → texto no fluxo de envio) roda no vitest, e o que sobra de
 * manual esta no bloco F10 do roteiro.
 *
 * O que o vitest NAO alcanca e o mesmo teto de sempre, so que agora do outro
 * lado da fronteira: microfone de verdade, permissao do Windows e qualidade
 * do audio vivem em Rust (`src-tauri/src/microfone.rs`, com a matematica
 * coberta por `cargo test`).
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  criarControleDitado,
  mensagemErroDitado,
  podeGravar,
  rotuloBotao,
  statusDitado,
  textoUtil,
  type EstadoDitado,
} from "./ditado";

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
    ["ocioso", "Clique para falar"],
    ["gravando", "Gravando — clique para enviar"],
    ["transcrevendo", "Transcrevendo…"],
  ])("botao em %s: %s", (estado, rotulo) => {
    expect(rotuloBotao(estado)).toBe(rotulo);
  });

  it("status: ocioso fica em silencio, os outros explicam a fase", () => {
    expect(statusDitado("ocioso")).toBeNull();
    expect(statusDitado("gravando")).toBe("Ouvindo — clique para enviar.");
    expect(statusDitado("transcrevendo")).toBe("Transcrevendo…");
  });
});

/** Um erro na forma do `ErroStt` de `lib/stt.ts`, sem importar o modulo. */
function erroStt(tipo: string, mensagem: string) {
  return Object.assign(new Error(mensagem), { name: "ErroStt", tipo });
}

describe("mensagemErroDitado", () => {
  it("erro do motor aparece com a mensagem que o Rust escreveu", () => {
    const recusa = erroStt(
      "microfone",
      "O Windows negou o acesso ao microfone. Abra Configuracoes > " +
        "Privacidade e seguranca > Microfone.",
    );
    const falha = mensagemErroDitado(recusa, "generica");
    expect(falha.mensagem).toContain("Privacidade e seguranca");
    expect(falha.modeloAusente).toBe(false);
  });

  it("modelo_ausente e sinalizado a parte — e oferta de download, nao erro", () => {
    const falha = mensagemErroDitado(
      erroStt("modelo_ausente", 'O modelo de voz "small" ainda nao foi baixado.'),
      "generica",
    );
    expect(falha.modeloAusente).toBe(true);
    expect(falha.mensagem).toContain("nao foi baixado");
  });

  it("erro fora do contrato cai na frase generica de quem chamou", () => {
    for (const cru of [new Error("boom"), "string crua", undefined, null]) {
      expect(mensagemErroDitado(cru, "Não consegui acessar o microfone.")).toEqual(
        { mensagem: "Não consegui acessar o microfone.", modeloAusente: false },
      );
    }
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

function depsFalsas(texto = "abrir o spotify") {
  return {
    calar: vi.fn(),
    iniciarGravacao: vi.fn(() => Promise.resolve({ taxa_hz: 48_000, canais: 1 })),
    pararETranscrever: vi.fn(() => Promise.resolve(texto)),
    cancelarGravacao: vi.fn(),
  };
}

function sinaisFalsos() {
  return {
    aoEstado: vi.fn((_estado: EstadoDitado) => {}),
    aoTexto: vi.fn((_texto: string) => {}),
    aoErro: vi.fn((_falha: { mensagem: string; modeloAusente: boolean }) => {}),
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  // O controlador loga a causa crua no console; os testes nao precisam dela.
  vi.spyOn(console, "error").mockImplementation(() => {});
});

describe("criarControleDitado — fluxo feliz", () => {
  it("cala o TTS ANTES de abrir o microfone, sempre", async () => {
    const deps = depsFalsas();
    const controle = criarControleDitado(deps, sinaisFalsos());

    await controle.iniciar();

    expect(deps.calar).toHaveBeenCalledTimes(1);
    expect(deps.calar.mock.invocationCallOrder[0]).toBeLessThan(
      deps.iniciarGravacao.mock.invocationCallOrder[0],
    );
  });

  it("grava, transcreve e entrega o texto aparado ao fluxo de envio", async () => {
    const deps = depsFalsas("  abrir o spotify  ");
    const sinais = sinaisFalsos();
    const controle = criarControleDitado(deps, sinais);

    await controle.iniciar();
    await controle.parar();

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
    const controle = criarControleDitado(depsFalsas("   "), sinais);

    await controle.iniciar();
    await controle.parar();

    expect(sinais.aoTexto).not.toHaveBeenCalled();
    expect(sinais.aoErro).not.toHaveBeenCalled();
    expect(sinais.aoEstado).toHaveBeenLastCalledWith("ocioso");
  });
});

describe("criarControleDitado — falhas", () => {
  it("recusa do microfone vira mensagem local e o estado nem sai do ocioso", async () => {
    const deps = depsFalsas();
    const recusa = erroStt(
      "microfone",
      "O Windows negou o acesso ao microfone. Abra Configuracoes > Privacidade.",
    );
    deps.iniciarGravacao.mockRejectedValue(recusa);
    const sinais = sinaisFalsos();
    const controle = criarControleDitado(deps, sinais);

    await controle.iniciar();

    expect(sinais.aoErro).toHaveBeenCalledWith({
      mensagem: recusa.message,
      modeloAusente: false,
    });
    expect(sinais.aoEstado).not.toHaveBeenCalled();
    // A causa crua foi para o console, prefixada — e o que o roteiro manda olhar.
    expect(console.error).toHaveBeenCalledWith(
      expect.stringContaining("[shogun]"),
      recusa,
    );
  });

  it("falha do motor vira erro local e volta ao ocioso", async () => {
    const deps = depsFalsas();
    deps.pararETranscrever.mockRejectedValue(new Error("motor caiu"));
    const sinais = sinaisFalsos();
    const controle = criarControleDitado(deps, sinais);

    await controle.iniciar();
    await controle.parar();

    expect(sinais.aoErro).toHaveBeenCalledWith({
      mensagem: "Não consegui transcrever o áudio.",
      modeloAusente: false,
    });
    expect(sinais.aoTexto).not.toHaveBeenCalled();
    expect(sinais.aoEstado).toHaveBeenLastCalledWith("ocioso");
  });

  it("modelo ausente chega a UI marcado como oferta de download", async () => {
    const deps = depsFalsas();
    deps.pararETranscrever.mockRejectedValue(
      erroStt("modelo_ausente", 'O modelo de voz "small" ainda nao foi baixado.'),
    );
    const sinais = sinaisFalsos();
    const controle = criarControleDitado(deps, sinais);

    await controle.iniciar();
    await controle.parar();

    expect(sinais.aoErro).toHaveBeenCalledWith(
      expect.objectContaining({ modeloAusente: true }),
    );
    expect(sinais.aoEstado).toHaveBeenLastCalledWith("ocioso");
  });
});

describe("criarControleDitado — corridas do push-to-talk", () => {
  it("soltar ANTES de o mic abrir CANCELA no Rust — o dispositivo ja abriu la", async () => {
    const deps = depsFalsas();
    let abrir!: () => void;
    deps.iniciarGravacao.mockReturnValue(
      new Promise((resolve) => {
        abrir = () => resolve({ taxa_hz: 48_000, canais: 1 });
      }),
    );
    const sinais = sinaisFalsos();
    const controle = criarControleDitado(deps, sinais);

    const iniciando = controle.iniciar();
    await controle.parar(); // soltou antes de o dispositivo abrir
    abrir();
    await iniciando;

    expect(deps.cancelarGravacao).toHaveBeenCalledTimes(1);
    expect(deps.pararETranscrever).not.toHaveBeenCalled();
    expect(sinais.aoEstado).not.toHaveBeenCalledWith("gravando");
  });

  it("cancelar enquanto abre tambem descarta", async () => {
    const deps = depsFalsas();
    let abrir!: () => void;
    deps.iniciarGravacao.mockReturnValue(
      new Promise((resolve) => {
        abrir = () => resolve({ taxa_hz: 48_000, canais: 1 });
      }),
    );
    const sinais = sinaisFalsos();
    const controle = criarControleDitado(deps, sinais);

    const iniciando = controle.iniciar();
    controle.cancelar();
    abrir();
    await iniciando;

    expect(deps.cancelarGravacao).toHaveBeenCalledTimes(1);
    expect(sinais.aoEstado).not.toHaveBeenCalled();
  });

  it("cancelar durante a gravacao descarta sem transcrever", async () => {
    const deps = depsFalsas();
    const sinais = sinaisFalsos();
    const controle = criarControleDitado(deps, sinais);

    await controle.iniciar();
    controle.cancelar();

    expect(deps.cancelarGravacao).toHaveBeenCalledTimes(1);
    expect(deps.pararETranscrever).not.toHaveBeenCalled();
    expect(sinais.aoEstado).toHaveBeenLastCalledWith("ocioso");
  });

  it("iniciar de novo durante a gravacao e no-op — nao abre segundo mic", async () => {
    const deps = depsFalsas();
    const controle = criarControleDitado(deps, sinaisFalsos());

    await controle.iniciar();
    await controle.iniciar();

    expect(deps.iniciarGravacao).toHaveBeenCalledTimes(1);
  });

  it("parar sem estar gravando e no-op", async () => {
    const deps = depsFalsas();
    const sinais = sinaisFalsos();
    const controle = criarControleDitado(deps, sinais);

    await controle.parar();

    expect(deps.pararETranscrever).not.toHaveBeenCalled();
    expect(sinais.aoEstado).not.toHaveBeenCalled();
    expect(sinais.aoErro).not.toHaveBeenCalled();
  });

  it("cancelar sem estar gravando nao chama o Rust a toa", () => {
    const deps = depsFalsas();
    criarControleDitado(deps, sinaisFalsos()).cancelar();
    expect(deps.cancelarGravacao).not.toHaveBeenCalled();
  });

  it("ciclo novo depois de um completo funciona — o controlador se rearma", async () => {
    const deps = depsFalsas("de novo");
    const sinais = sinaisFalsos();
    const controle = criarControleDitado(deps, sinais);

    await controle.iniciar();
    await controle.parar();
    await controle.iniciar();
    await controle.parar();

    expect(sinais.aoTexto).toHaveBeenCalledTimes(2);
  });

  it("um ciclo que falhou na abertura nao trava o proximo", async () => {
    const deps = depsFalsas();
    deps.iniciarGravacao.mockRejectedValueOnce(erroStt("microfone", "ocupado"));
    const sinais = sinaisFalsos();
    const controle = criarControleDitado(deps, sinais);

    await controle.iniciar();
    await controle.iniciar();
    await controle.parar();

    expect(sinais.aoTexto).toHaveBeenCalledTimes(1);
  });
});
