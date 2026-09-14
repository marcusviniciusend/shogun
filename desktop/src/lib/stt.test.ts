/**
 * Testes do wrapper de STT — `invoke` e `listen` mockados, no padrao da
 * suite: modulo puro, plugin dublado, e o teto de honestidade registrado —
 * o motor whisper de verdade (Rust + modelo de ~466 MB) fica fora do vitest;
 * transcricao com som real e teste manual (roteiro F9 no PR).
 *
 * O que se prende aqui e o contrato do wrapper: a forma com que o PCM vai ao
 * `invoke`, a traducao de `{ tipo, mensagem }` em `ErroStt`, o ciclo de vida
 * do listener de progresso e os guardas locais (gravacao vazia).
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";

import {
  ErroStt,
  EVENTO_PROGRESSO_STT,
  MODELO_STT_PADRAO,
  baixarModeloStt,
  statusModeloStt,
  transcrever,
  type ProgressoDownloadStt,
  type StatusModeloStt,
} from "./stt";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));
vi.mock("@tauri-apps/api/event", () => ({ listen: vi.fn() }));

const invokeMock = vi.mocked(invoke);
const listenMock = vi.mocked(listen);

/** Um status de modelo plausivel, para as respostas dubladas. */
function status(presente: boolean): StatusModeloStt {
  return {
    modelo: "small",
    arquivo: "ggml-small.bin",
    presente,
    tamanho_bytes: presente ? 487601967 : null,
    tamanho_esperado_bytes: 487601967,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("transcrever", () => {
  it("manda o PCM como array simples e devolve o texto do motor", async () => {
    invokeMock.mockResolvedValue("abrir a calculadora");
    const pcm = new Float32Array([0.1, -0.2, 0.3]);

    const texto = await transcrever(pcm);

    expect(texto).toBe("abrir a calculadora");
    expect(invokeMock).toHaveBeenCalledWith("stt_transcrever", {
      // Array simples, nao Float32Array: o IPC serializa JSON, e typed array
      // nao sobrevive ao JSON.stringify.
      pcm: [expect.closeTo(0.1), expect.closeTo(-0.2), expect.closeTo(0.3)],
      modelo: MODELO_STT_PADRAO,
    });
    const enviado = invokeMock.mock.calls[0][1] as { pcm: unknown };
    expect(Array.isArray(enviado.pcm)).toBe(true);
  });

  it("modelo explicito e repassado — a troca small/base e runtime", async () => {
    invokeMock.mockResolvedValue("oi");

    await transcrever(new Float32Array([0.1]), "base");

    expect(invokeMock).toHaveBeenCalledWith(
      "stt_transcrever",
      expect.objectContaining({ modelo: "base" }),
    );
  });

  it("gravacao vazia falha como `audio` sem nem chamar o Rust", async () => {
    await expect(transcrever(new Float32Array(0))).rejects.toMatchObject({
      name: "ErroStt",
      tipo: "audio",
    });
    expect(invokeMock).not.toHaveBeenCalled();
  });

  it("modelo nao baixado vira ErroStt `modelo_ausente` com a mensagem do Rust", async () => {
    invokeMock.mockRejectedValue({
      tipo: "modelo_ausente",
      mensagem: "O modelo de voz \"small\" ainda nao foi baixado.",
    });

    const erro = await transcrever(new Float32Array([0.1])).catch((e) => e);

    expect(erro).toBeInstanceOf(ErroStt);
    expect(erro.tipo).toBe("modelo_ausente");
    expect(erro.message).toBe(
      'O modelo de voz "small" ainda nao foi baixado.',
    );
  });

  it("tipo fora do contrato preserva a mensagem mas cai em `desconhecido`", async () => {
    // Rust mais novo que o wrapper: a mensagem ainda e exibivel, o tipo nao
    // pode enganar a UI.
    invokeMock.mockRejectedValue({
      tipo: "gpu_em_chamas",
      mensagem: "Algo novo aconteceu.",
    });

    const erro = await transcrever(new Float32Array([0.1])).catch((e) => e);

    expect(erro.tipo).toBe("desconhecido");
    expect(erro.message).toBe("Algo novo aconteceu.");
  });

  it("erro cru do IPC vira `desconhecido` com mensagem generica e causa preservada", async () => {
    const consoleError = vi
      .spyOn(console, "error")
      .mockImplementation(() => {});
    invokeMock.mockRejectedValue("panicked at ...");

    const erro = await transcrever(new Float32Array([0.1])).catch((e) => e);

    expect(erro).toBeInstanceOf(ErroStt);
    expect(erro.tipo).toBe("desconhecido");
    expect(erro.message).toBe("O motor de voz falhou de forma inesperada.");
    // A causa crua sobrevive para diagnostico — no erro e no console.
    expect(erro.causa).toBe("panicked at ...");
    expect(consoleError).toHaveBeenCalled();
    consoleError.mockRestore();
  });
});

describe("statusModeloStt", () => {
  it("consulta o modelo padrao quando nenhum e pedido", async () => {
    invokeMock.mockResolvedValue(status(true));

    const s = await statusModeloStt();

    expect(s.presente).toBe(true);
    expect(invokeMock).toHaveBeenCalledWith("stt_modelo_status", {
      modelo: MODELO_STT_PADRAO,
    });
  });

  it("erro estruturado do Rust tambem passa pelo funil de traducao", async () => {
    invokeMock.mockRejectedValue({
      tipo: "modelo_desconhecido",
      mensagem: "Modelo de voz \"enorme\" nao e conhecido.",
    });

    await expect(statusModeloStt()).rejects.toMatchObject({
      name: "ErroStt",
      tipo: "modelo_desconhecido",
    });
  });
});

describe("baixarModeloStt", () => {
  it("sem callback de progresso, nao registra listener nenhum", async () => {
    invokeMock.mockResolvedValue(status(true));

    await baixarModeloStt();

    expect(listenMock).not.toHaveBeenCalled();
    expect(invokeMock).toHaveBeenCalledWith("stt_baixar_modelo", {
      modelo: MODELO_STT_PADRAO,
    });
  });

  it("registra o listener ANTES do comando e repassa cada progresso", async () => {
    const desregistrar = vi.fn();
    listenMock.mockResolvedValue(desregistrar);
    invokeMock.mockResolvedValue(status(true));
    const progressos: ProgressoDownloadStt[] = [];

    await baixarModeloStt("small", (p) => progressos.push(p));

    expect(listenMock).toHaveBeenCalledWith(
      EVENTO_PROGRESSO_STT,
      expect.any(Function),
    );
    // Listener primeiro, comando depois — senao o comeco do download passa
    // sem barra de progresso.
    expect(listenMock.mock.invocationCallOrder[0]).toBeLessThan(
      invokeMock.mock.invocationCallOrder[0],
    );

    // Simula dois eventos chegando pelo canal do Tauri.
    const aoEvento = listenMock.mock.calls[0][1];
    const progresso = (baixado: number): ProgressoDownloadStt => ({
      modelo: "small",
      baixado_bytes: baixado,
      total_bytes: 487601967,
    });
    aoEvento({ event: EVENTO_PROGRESSO_STT, id: 1, payload: progresso(4) });
    aoEvento({ event: EVENTO_PROGRESSO_STT, id: 1, payload: progresso(8) });

    expect(progressos.map((p) => p.baixado_bytes)).toEqual([4, 8]);
    // Terminou: o listener morre com o download.
    expect(desregistrar).toHaveBeenCalledTimes(1);
  });

  it("desregistra o listener mesmo quando o download falha", async () => {
    const desregistrar = vi.fn();
    listenMock.mockResolvedValue(desregistrar);
    invokeMock.mockRejectedValue({
      tipo: "integridade",
      mensagem: "O arquivo baixado nao passou na verificacao de integridade.",
    });

    await expect(baixarModeloStt("small", () => {})).rejects.toMatchObject({
      tipo: "integridade",
    });

    expect(desregistrar).toHaveBeenCalledTimes(1);
  });

  it("erros de download sao seguros de repetir e chegam com o tipo certo", async () => {
    invokeMock.mockRejectedValue({
      tipo: "download",
      mensagem: "O download do modelo foi interrompido no meio.",
    });

    const erro = await baixarModeloStt().catch((e) => e);

    expect(erro).toBeInstanceOf(ErroStt);
    expect(erro.tipo).toBe("download");
  });
});
