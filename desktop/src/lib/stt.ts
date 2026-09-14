/**
 * STT do Shogun — wrapper TS do motor whisper.cpp local (comandos Tauri).
 *
 * O motor vive no processo Rust (`src-tauri/src/stt.rs`): whisper.cpp em CPU,
 * modelo ggml oficial baixado no primeiro uso (fora do repositorio e do
 * instalador), `language: "pt"` fixado. Este modulo e a UNICA porta de
 * entrada do frontend para ele — quem captura audio chama `transcrever()` e
 * recebe texto, sem saber qual motor esta por tras (mesmo desenho de
 * `voz.ts`, onde `falar()` esconde o speechSynthesis; nuvem entraria como
 * upgrade atras desta mesma interface).
 *
 * Contrato do audio: PCM 16 kHz, mono, `Float32Array` com amostras em
 * -1.0..1.0 — o formato que o whisper.cpp consome e que a captura via
 * AudioWorklet produz. A serializacao pelo `invoke` copia o buffer; para
 * falas de comando (segundos), o custo e desprezivel (~64 KB/s de fala).
 *
 * Erros: o Rust devolve `{ tipo, mensagem }` ja em portugues sem acentos e
 * sem caminho de disco; aqui isso vira `ErroStt` (mesmo padrao do
 * `ErroComando` em `api.ts`) — a UI decide a reacao pelo `tipo`, nunca por
 * pattern-matching na mensagem.
 */
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";

/**
 * Modelos ggml oficiais que o motor sabe baixar. `small` e o aprovado
 * (qualidade/custo para pt); `base` e o plano B de latencia. A troca e
 * runtime — nenhuma recompilacao.
 */
export type ModeloStt = "tiny" | "base" | "small" | "medium";

/** O candidato aprovado no desenho (docs/stt-desktop-design.md, secao 8). */
export const MODELO_STT_PADRAO: ModeloStt = "small";

/** Situacao de um modelo no disco, como o Rust reporta. */
export interface StatusModeloStt {
  modelo: string;
  arquivo: string;
  /** Presente E com o tamanho esperado — truncado conta como ausente. */
  presente: boolean;
  tamanho_bytes: number | null;
  tamanho_esperado_bytes: number;
}

/** Payload dos eventos de progresso emitidos durante o download. */
export interface ProgressoDownloadStt {
  modelo: string;
  baixado_bytes: number;
  total_bytes: number;
}

/** Nome do evento Tauri de progresso — precisa bater com o Rust. */
export const EVENTO_PROGRESSO_STT = "stt-download-progresso";

/**
 * Categoria da falha, espelhando o `tipo` do `ErroStt` Rust:
 *
 * - `modelo_ausente`: o modelo nao foi baixado — a UI oferece o download.
 * - `modelo_desconhecido`: nome de modelo invalido (bug de chamada, nao de
 *   usuario).
 * - `download` / `integridade`: falha ao baixar ou validar o modelo — ambas
 *   terminam com "tente de novo" e sao seguras de repetir.
 * - `motor`: whisper falhou (carga ou transcricao) — pode ser arquivo
 *   corrompido; re-baixar o modelo e o proximo passo razoavel.
 * - `audio`: a gravacao chegou vazia — problema de captura, nao de motor.
 * - `desconhecido`: erro fora do contrato (bug); a causa crua vai no console.
 */
export type TipoErroStt =
  | "modelo_desconhecido"
  | "modelo_ausente"
  | "download"
  | "integridade"
  | "motor"
  | "audio"
  | "desconhecido";

const TIPOS_CONHECIDOS: readonly string[] = [
  "modelo_desconhecido",
  "modelo_ausente",
  "download",
  "integridade",
  "motor",
  "audio",
];

/** Erro ja traduzido para mensagem exibivel — irmao do `ErroComando`. */
export class ErroStt extends Error {
  readonly tipo: TipoErroStt;
  /** Causa crua, para log e diagnostico. Nao e mostrada ao usuario. */
  readonly causa?: unknown;

  constructor(mensagem: string, tipo: TipoErroStt, causa?: unknown) {
    super(mensagem);
    this.name = "ErroStt";
    this.tipo = tipo;
    this.causa = causa;
  }
}

/**
 * Traduz a rejeicao do `invoke` num `ErroStt`.
 *
 * O contrato com o Rust e `{ tipo, mensagem }` com mensagem ja exibivel.
 * Um `tipo` fora da lista (comando Rust mais novo que este wrapper) preserva
 * a mensagem mas cai em `desconhecido`; qualquer outra forma de erro (string
 * crua do Tauri, excecao de IPC) vira o generico — com a causa no console,
 * unico lugar onde o detalhe cru sobrevive.
 */
function traduzirErro(e: unknown): ErroStt {
  if (e instanceof ErroStt) return e;
  if (
    typeof e === "object" &&
    e !== null &&
    "tipo" in e &&
    "mensagem" in e &&
    typeof (e as { mensagem: unknown }).mensagem === "string"
  ) {
    const { tipo, mensagem } = e as { tipo: unknown; mensagem: string };
    return new ErroStt(
      mensagem,
      TIPOS_CONHECIDOS.includes(tipo as string)
        ? (tipo as TipoErroStt)
        : "desconhecido",
      e,
    );
  }
  console.error("[shogun] stt: erro fora do contrato:", e);
  return new ErroStt(
    "O motor de voz falhou de forma inesperada.",
    "desconhecido",
    e,
  );
}

/**
 * Verifica se o modelo esta baixado e integro no disco. Barato (um stat) —
 * pode ser chamado a cada abertura da tela de voz.
 */
export async function statusModeloStt(
  modelo: ModeloStt = MODELO_STT_PADRAO,
): Promise<StatusModeloStt> {
  try {
    return await invoke<StatusModeloStt>("stt_modelo_status", { modelo });
  } catch (e) {
    throw traduzirErro(e);
  }
}

/**
 * Baixa o modelo no primeiro uso (~466 MB no small), com validacao de
 * integridade no Rust. Idempotente: modelo ja integro devolve na hora sem
 * rede. `aoProgredir` recebe os eventos de progresso enquanto o download
 * corre — o listener e registrado antes do comando e SEMPRE desregistrado ao
 * final, com sucesso ou erro.
 */
export async function baixarModeloStt(
  modelo: ModeloStt = MODELO_STT_PADRAO,
  aoProgredir?: (progresso: ProgressoDownloadStt) => void,
): Promise<StatusModeloStt> {
  let parar: (() => void) | null = null;
  if (aoProgredir) {
    parar = await listen<ProgressoDownloadStt>(EVENTO_PROGRESSO_STT, (ev) => {
      aoProgredir(ev.payload);
    });
  }
  try {
    return await invoke<StatusModeloStt>("stt_baixar_modelo", { modelo });
  } catch (e) {
    throw traduzirErro(e);
  } finally {
    parar?.();
  }
}

/**
 * Transcreve uma fala para texto em portugues.
 *
 * `pcm`: PCM 16 kHz mono, Float32Array (-1.0..1.0). Gravacao vazia falha
 * aqui mesmo, sem ir ao Rust — e erro de captura, nao de motor.
 *
 * A primeira chamada carrega o modelo na memoria (segundos); as seguintes
 * reutilizam o contexto. Modelo nao baixado rejeita com `modelo_ausente` —
 * a UI oferece `baixarModeloStt()` e tenta de novo.
 */
export async function transcrever(
  pcm: Float32Array,
  modelo: ModeloStt = MODELO_STT_PADRAO,
): Promise<string> {
  if (pcm.length === 0) {
    throw new ErroStt(
      "Nenhum audio capturado — a gravacao veio vazia.",
      "audio",
    );
  }
  try {
    return await invoke<string>("stt_transcrever", {
      pcm: Array.from(pcm),
      modelo,
    });
  } catch (e) {
    throw traduzirErro(e);
  }
}
