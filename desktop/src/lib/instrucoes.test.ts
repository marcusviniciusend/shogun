/**
 * Testes da regra de consumo do contrato: `text` x `fallback_text`.
 *
 * A regra vive na docstring de `ClientInstruction` (nos dois `shared/`) e nao
 * aparece em tipo nenhum — mudar o comportamento aqui nao quebra o `tsc` nem
 * a paridade de contratos. Ou seja: estes testes sao a unica rede mecanica
 * sobre ela.
 *
 * O invariante que amarra tudo: `executarInstrucoes` devolve SEMPRE
 * exatamente um dos dois textos. Nunca os dois concatenados, nunca vazio —
 * senao o TTS anuncia "Pedi para abrir o X" e se contradiz em seguida, ou
 * fica mudo.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CommandResponseWire } from "./types";
import { executarInstrucoes, normalizar } from "./instrucoes";

const { criar, spawn } = vi.hoisted(() => ({
  criar: vi.fn(),
  spawn: vi.fn(),
}));

// O plugin de shell do Tauri so existe dentro do app; aqui interessa apenas
// COM O QUE ele seria chamado, nunca executar de verdade.
vi.mock("@tauri-apps/plugin-shell", () => ({
  Command: { create: criar },
}));

const TEXTO = "Pedi para este aparelho abrir o Spotify, Marcus.";
const FALLBACK = "Nao consegui abrir o Spotify neste aparelho, Marcus.";

function resposta(instruction: unknown): CommandResponseWire {
  return {
    session_id: "s1",
    text: TEXTO,
    actions: [{ agent: "sistema", status: "ok", instruction }],
  } as CommandResponseWire;
}

beforeEach(() => {
  vi.clearAllMocks();
  spawn.mockResolvedValue(undefined);
  criar.mockReturnValue({ spawn });
  // A falha esperada de um caso registra no console de proposito; silenciar
  // mantem a saida do teste legivel sem esconder o comportamento.
  vi.spyOn(console, "warn").mockImplementation(() => {});
  vi.spyOn(console, "error").mockImplementation(() => {});
});

describe("normalizar", () => {
  it.each([
    ["Calculadora", "calculadora"],
    ["  calculadora  ", "calculadora"],
    ["CALCULADORA", "calculadora"],
    ["Explorador   de  Arquivos", "explorador de arquivos"],
    ["Área de Trabalho", "area de trabalho"],
    ["Navegadoŕ", "navegador"],
  ])('"%s" vira "%s"', (entrada, esperado) => {
    expect(normalizar(entrada)).toBe(esperado);
  });
});

describe("executarInstrucoes — regra text x fallback_text", () => {
  it("sem instrucao nenhuma, devolve o text e nao chama o shell", async () => {
    const semInstrucao = {
      session_id: "s1",
      text: TEXTO,
      actions: [{ agent: "pendencias", status: "ok", instruction: null }],
    } as CommandResponseWire;

    expect(await executarInstrucoes(semInstrucao)).toBe(TEXTO);
    expect(criar).not.toHaveBeenCalled();
  });

  it("app do mapa com spawn aceito devolve o text", async () => {
    const r = resposta({ type: "open_app", app: "Spotify", fallback_text: FALLBACK });

    expect(await executarInstrucoes(r)).toBe(TEXTO);
    expect(criar).toHaveBeenCalledWith("abrir-spotify", ["spotify:"]);
  });

  it("sinonimo resolve para o comando do mapa", async () => {
    const r = resposta({ type: "open_app", app: "Chrome", fallback_text: FALLBACK });

    expect(await executarInstrucoes(r)).toBe(TEXTO);
    expect(criar).toHaveBeenCalledWith("abrir-navegador", ["https://www.google.com"]);
  });

  it("spawn recusado pelo Tauri cai no fallback_text", async () => {
    spawn.mockRejectedValueOnce(new Error("permissao negada"));
    const r = resposta({ type: "open_app", app: "Spotify", fallback_text: FALLBACK });

    expect(await executarInstrucoes(r)).toBe(FALLBACK);
  });

  it("app fora do mapa curado cai no fallback_text sem tentar spawn", async () => {
    const r = resposta({ type: "open_app", app: "Photoshop", fallback_text: FALLBACK });

    expect(await executarInstrucoes(r)).toBe(FALLBACK);
    expect(criar).not.toHaveBeenCalled();
  });

  it("type desconhecido (cliente antigo, servidor novo) cai no fallback_text", async () => {
    const r = resposta({ type: "open_url", app: "Spotify", fallback_text: FALLBACK });

    expect(await executarInstrucoes(r)).toBe(FALLBACK);
    expect(criar).not.toHaveBeenCalled();
  });

  it("pega a primeira action que carrega instrucao, ignorando as informativas", async () => {
    const r = {
      session_id: "s1",
      text: TEXTO,
      actions: [
        { agent: "pendencias", status: "ok", detail: "0 pendencias", instruction: null },
        {
          agent: "sistema",
          status: "ok",
          instruction: { type: "open_app", app: "Calculadora", fallback_text: FALLBACK },
        },
      ],
    } as CommandResponseWire;

    expect(await executarInstrucoes(r)).toBe(TEXTO);
    expect(criar).toHaveBeenCalledWith("abrir-calculadora", []);
  });

  it.each([
    ["sucesso", "Spotify", false, TEXTO],
    ["falha de spawn", "Spotify", true, FALLBACK],
    ["fora do mapa", "Photoshop", false, FALLBACK],
  ])(
    "em %s devolve exatamente um dos dois textos, nunca os dois nem nenhum",
    async (_caso, app, falha, esperado) => {
      if (falha) spawn.mockRejectedValueOnce(new Error("x"));
      const r = resposta({ type: "open_app", app, fallback_text: FALLBACK });

      const saida = await executarInstrucoes(r);

      expect(saida).toBe(esperado);
      expect(saida).not.toBe("");
      // O outro texto nao pode aparecer junto: TTS que fala os dois se
      // contradiz no mesmo folego.
      const outro = esperado === TEXTO ? FALLBACK : TEXTO;
      expect(saida).not.toContain(outro);
    },
  );
});
