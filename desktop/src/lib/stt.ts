/**
 * STT do Shogun — wrapper TS do motor de voz local (comandos Tauri).
 *
 * O motor inteiro vive no processo Rust: a CAPTURA em `src-tauri/src/
 * microfone.rs` (cpal/WASAPI) e a TRANSCRICAO em `src-tauri/src/stt.rs`
 * (whisper.cpp em CPU, modelo ggml baixado no primeiro uso, `language: "pt"`
 * fixado). Este modulo e a UNICA porta de entrada do frontend para ele.
 *
 * **O audio nunca passa por aqui.** Ate o PR #62 a captura era
 * `getUserMedia` no WebView2 e o PCM atravessava o IPC como array JSON;
 * a decisao que trouxe o cpal mudou isso. O que este modulo manda e recebe
 * agora sao so comandos e texto: `iniciarGravacao()` abre o microfone,
 * `pararGravacaoETranscrever()` fecha e devolve a fala ja transcrita. O PCM
 * nasce e morre em Rust.
 *
 * Erros: o Rust devolve `{ tipo, mensagem }` ja em portugues sem acentos e
 * sem caminho de disco; aqui isso vira `ErroStt` (mesmo padrao do
 * `ErroComando` em `api.ts`) — a UI decide a reacao pelo `tipo`, nunca por
 * pattern-matching na mensagem.
 */
import { invoke, isTauri } from "@tauri-apps/api/core";
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

/**
 * O que o Rust conta sobre a gravacao recem-aberta: a taxa REAL do
 * dispositivo (o Windows costuma entregar 44,1 ou 48 kHz) e a contagem de
 * canais do PCM que sai de la — sempre 1, porque a mesclagem para mono
 * acontece no callback de audio. Nao decide nada no TS; serve ao indicador
 * de gravacao e ao diagnostico do roteiro manual.
 */
export interface InfoGravacao {
  taxa_hz: number;
  canais: number;
}

/** Nome do evento Tauri de progresso — precisa bater com o Rust. */
export const EVENTO_PROGRESSO_STT = "stt-download-progresso";

/**
 * Categoria da falha, espelhando o `tipo` do `ErroStt` Rust:
 *
 * - `modelo_ausente`: o modelo nao foi baixado — NAO e um erro comum, e o
 *   gatilho para a UI oferecer o download (ver `baixarModeloStt`).
 * - `modelo_desconhecido`: nome de modelo invalido (bug de chamada, nao de
 *   usuario).
 * - `download` / `integridade`: falha ao baixar ou validar o modelo — ambas
 *   terminam com "tente de novo" e sao seguras de repetir.
 * - `motor`: whisper falhou (carga ou transcricao) — pode ser arquivo
 *   corrompido; re-baixar o modelo e o proximo passo razoavel.
 * - `microfone`: o dispositivo nao abriu — permissao negada pelo Windows,
 *   nenhum microfone, microfone ocupado por outro aplicativo.
 * - `gravacao`: o ciclo foi chamado fora de ordem (parar sem ter iniciado,
 *   iniciar duas vezes). Bug de fiacao, nao de usuario.
 * - `audio`: a gravacao chegou vazia — o microfone abriu mas nada chegou.
 * - `desconhecido`: erro fora do contrato (bug); a causa crua vai no console.
 */
export type TipoErroStt =
  | "modelo_desconhecido"
  | "modelo_ausente"
  | "download"
  | "integridade"
  | "motor"
  | "microfone"
  | "gravacao"
  | "audio"
  | "desconhecido";

const TIPOS_CONHECIDOS: readonly string[] = [
  "modelo_desconhecido",
  "modelo_ausente",
  "download",
  "integridade",
  "motor",
  "microfone",
  "gravacao",
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
 * Ha motor de voz neste ambiente?
 *
 * O motor e Rust: existe quando o app roda dentro do Tauri, e nao existe no
 * `vite dev` aberto no navegador (onde `invoke` nem tem para quem falar).
 * E o GATE do botao de falar — capacidade detectada em runtime, e nao mais
 * `import.meta.env.DEV`: agora que a fiacao e real, esconder o microfone no
 * build de producao seria esconder o recurso de quem o tem.
 */
export function sttDisponivel(): boolean {
  return isTauri();
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

/* ------------------------------------------------------- ciclo de gravacao */

/**
 * Abre o microfone no Rust e comeca a gravar (push-to-talk pressionado).
 *
 * Falha como `microfone` quando o Windows nega a permissao, quando nao ha
 * dispositivo de entrada ou quando outro aplicativo o segura.
 */
export async function iniciarGravacao(): Promise<InfoGravacao> {
  try {
    return await invoke<InfoGravacao>("microfone_iniciar");
  } catch (e) {
    throw traduzirErro(e);
  }
}

/**
 * Fecha o microfone e devolve a fala transcrita (push-to-talk solto).
 *
 * Um comando so, e nao "parar" seguido de "transcrever": o PCM nao existe
 * no TS para haver um passo intermediario. Texto vazio significa que nada
 * foi reconhecido.
 *
 * A primeira chamada carrega o modelo na memoria (segundos); as seguintes
 * reutilizam o contexto. Modelo nao baixado rejeita com `modelo_ausente` —
 * a UI oferece `baixarModeloStt()` e o usuario tenta de novo.
 */
export async function pararGravacaoETranscrever(
  modelo: ModeloStt = MODELO_STT_PADRAO,
): Promise<string> {
  try {
    return await invoke<string>("microfone_parar_e_transcrever", { modelo });
  } catch (e) {
    throw traduzirErro(e);
  }
}

/**
 * Fecha o microfone DESCARTANDO o audio (desistencia, troca de tela,
 * desmontagem do componente).
 *
 * Nunca rejeita: quem cancela esta limpando, muitas vezes sem saber se havia
 * gravacao aberta, e nao tem o que fazer com uma falha. O detalhe vai para o
 * console. No Rust o comando ja e idempotente.
 */
export async function cancelarGravacao(): Promise<void> {
  try {
    await invoke<void>("microfone_cancelar");
  } catch (e) {
    console.error("[shogun] stt: cancelar gravacao falhou:", traduzirErro(e));
  }
}
