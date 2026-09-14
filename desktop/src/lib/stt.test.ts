/**
 * Testes do wrapper de STT — `invoke`, `listen` e `isTauri` mockados, no
 * padrao da suite: modulo puro, plugin dublado, e o teto de honestidade
 * registrado — o motor de verdade (captura cpal + whisper + modelo de
 * ~466 MB) fica em Rust, fora do vitest; audio real e teste manual (roteiro
 * F9 no PR).
 *
 * O que se prende aqui e o contrato do wrapper: os comandos e argumentos que
 * cada funcao manda ao Rust, a traducao de `{ tipo, mensagem }` em `ErroStt`,
 * o ciclo de vida do listener de progresso e a aritmetica de exibicao do
 * download. PCM nao aparece em teste nenhum — desde a troca para a captura
 * nativa, o audio nao passa mais por este lado.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { invoke, isTauri } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";

import {
  ErroStt,
  EVENTO_PROGRESSO_STT,
  MODELO_STT_PADRAO,
  baixarModeloStt,
  cancelarGravacao,
  formatarProgresso,
  iniciarGravacao,
  megabytes,
  pararGravacaoETranscrever,
  percentualDownload,
  sttDisponivel,
  statusModeloStt,
  type ProgressoDownloadStt,
  type StatusModeloStt,
} from "./stt";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn(), isTauri: vi.fn() }));
vi.mock("@tauri-apps/api/event", () => ({ listen: vi.fn() }));

const invokeMock = vi.mocked(invoke);
const listenMock = vi.mocked(listen);
const isTauriMock = vi.mocked(isTauri);

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

describe("sttDisponivel", () => {
  it("ha motor de voz quando o app roda dentro do Tauri, e so entao", () => {
    isTauriMock.mockReturnValue(true);
    expect(sttDisponivel()).toBe(true);
    isTauriMock.mockReturnValue(false);
    expect(sttDisponivel()).toBe(false);
  });
});

describe("progresso do download", () => {
  const progresso = (baixado: number, total = 487601967): ProgressoDownloadStt => ({
    modelo: "small",
    baixado_bytes: baixado,
    total_bytes: total,
  });

  it("percentual e inteiro e nunca sai de 0..100", () => {
    expect(percentualDownload(progresso(0))).toBe(0);
    expect(percentualDownload(progresso(487601967))).toBe(100);
    expect(percentualDownload(progresso(243800983))).toBe(50);
    // Servidor mentindo no content-length nao produz 137%.
    expect(percentualDownload(progresso(999999999))).toBe(100);
  });

  it("total zerado nao vira divisao por zero", () => {
    expect(percentualDownload(progresso(10, 0))).toBe(0);
  });

  it("megabytes e a unidade em que 466 MB significa alguma coisa", () => {
    expect(megabytes(487601967)).toBe(465);
    expect(megabytes(0)).toBe(0);
  });

  it("a linha exibivel junta baixado, total e percentual", () => {
    expect(formatarProgresso(progresso(243800983))).toBe(
      "233 MB de 465 MB (50%)",
    );
  });
});

describe("ciclo de gravacao", () => {
  it("iniciar abre o microfone no Rust e devolve a taxa real do dispositivo", async () => {
    invokeMock.mockResolvedValue({ taxa_hz: 48_000, canais: 1 });

    const info = await iniciarGravacao();

    expect(info).toEqual({ taxa_hz: 48_000, canais: 1 });
    // Sem argumentos: nao ha nada que o TS possa configurar na captura.
    expect(invokeMock).toHaveBeenCalledWith("microfone_iniciar");
  });

  it("permissao negada pelo Windows chega tipada como `microfone`", async () => {
    invokeMock.mockRejectedValue({
      tipo: "microfone",
      mensagem:
        "O Windows negou o acesso ao microfone. Abra Configuracoes > " +
        "Privacidade e seguranca > Microfone.",
    });

    const erro = await iniciarGravacao().catch((e) => e);

    expect(erro).toBeInstanceOf(ErroStt);
    expect(erro.tipo).toBe("microfone");
    expect(erro.message).toContain("Privacidade e seguranca");
  });

  it("parar devolve o texto — nenhum PCM atravessa o IPC", async () => {
    invokeMock.mockResolvedValue("abrir a calculadora");

    const texto = await pararGravacaoETranscrever();

    expect(texto).toBe("abrir a calculadora");
    expect(invokeMock).toHaveBeenCalledWith("microfone_parar_e_transcrever", {
      modelo: MODELO_STT_PADRAO,
    });
    // O unico argumento e o nome do modelo: nada de amostras de audio.
    expect(invokeMock.mock.calls[0][1]).toEqual({ modelo: MODELO_STT_PADRAO });
  });

  it("modelo explicito e repassado — a troca small/base e runtime", async () => {
    invokeMock.mockResolvedValue("oi");

    await pararGravacaoETranscrever("base");

    expect(invokeMock).toHaveBeenCalledWith(
      "microfone_parar_e_transcrever",
      expect.objectContaining({ modelo: "base" }),
    );
  });

  it("modelo nao baixado vira ErroStt `modelo_ausente` com a mensagem do Rust", async () => {
    invokeMock.mockRejectedValue({
      tipo: "modelo_ausente",
      mensagem:
        'O modelo de voz "small" ainda nao foi baixado. Baixe o modelo antes ' +
        "de usar o microfone.",
    });

    const erro = await pararGravacaoETranscrever().catch((e) => e);

    expect(erro).toBeInstanceOf(ErroStt);
    expect(erro.tipo).toBe("modelo_ausente");
    expect(erro.message).toContain("ainda nao foi baixado");
  });

  it("tipo fora do contrato preserva a mensagem mas cai em `desconhecido`", async () => {
    invokeMock.mockRejectedValue({
      tipo: "algo_que_este_wrapper_nao_conhece",
      mensagem: "Mensagem que o Rust ja escreveu para o usuario.",
    });

    const erro = await pararGravacaoETranscrever().catch((e) => e);

    expect(erro.tipo).toBe("desconhecido");
    expect(erro.message).toBe("Mensagem que o Rust ja escreveu para o usuario.");
  });

  it("erro cru do IPC vira `desconhecido` com mensagem generica e causa preservada", async () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    invokeMock.mockRejectedValue("panicked at ...");

    const erro = await pararGravacaoETranscrever().catch((e) => e);

    expect(erro.tipo).toBe("desconhecido");
    expect(erro.message).toBe("O motor de voz falhou de forma inesperada.");
    expect(erro.causa).toBe("panicked at ...");
    expect(consoleError).toHaveBeenCalled();
    consoleError.mockRestore();
  });

  it("cancelar chama o Rust e NUNCA rejeita — quem limpa nao trata erro", async () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    invokeMock.mockResolvedValue(undefined);

    await expect(cancelarGravacao()).resolves.toBeUndefined();
    expect(invokeMock).toHaveBeenCalledWith("microfone_cancelar");

    invokeMock.mockRejectedValue({ tipo: "gravacao", mensagem: "nada aberto" });
    await expect(cancelarGravacao()).resolves.toBeUndefined();
    expect(consoleError).toHaveBeenCalled();
    consoleError.mockRestore();
  });
});
