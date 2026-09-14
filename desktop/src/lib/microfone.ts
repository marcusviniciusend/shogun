/**
 * Captura de audio do microfone — `getUserMedia` no WebView2, PCM 16 kHz mono
 * extraido no cliente (decisao aprovada em docs/stt-desktop-design.md §3/§8).
 *
 * O modulo tem duas camadas, no padrao de `voz.ts`:
 *
 *   - funcoes PURAS de processamento (media de canais, concatenacao de blocos,
 *     reamostragem) — cobertas por vitest com arrays sinteticos;
 *   - a fiacao IMPURA (`iniciarCaptura`) por cima das APIs do WebView2
 *     (`getUserMedia` + `AudioContext` + `AudioWorklet`) — testada com globais
 *     dubladas; o comportamento real (prompt de permissao, som de verdade) e
 *     verificacao manual, como o TTS no bloco F8 do roteiro.
 *
 * O PCM entregue por `parar()` e o formato que o whisper.cpp consome:
 * `Float32Array`, mono, `TAXA_ALVO` Hz, amostras em [-1, 1]. E exatamente o
 * que o transcritor injetado (`lib/ditado.ts`) recebe — a costura com o motor
 * de STT (branch do `lib/stt.ts`) passa por esse contrato.
 *
 * Nenhuma permissao nova de Tauri: o acesso a midia do webview nao passa pelo
 * capabilities (governa plugins e comandos), so pela chave de privacidade de
 * microfone do Windows e pelo fluxo de permissao do proprio WebView2 (§3.3 do
 * desenho).
 */

/** Taxa de amostragem que o motor de STT consome (whisper.cpp: 16 kHz). */
export const TAXA_ALVO = 16_000;

/** Falta de API no ambiente (webview antigo, testes) — nao e recusa do usuario. */
export class CapturaIndisponivelError extends Error {
  constructor(detalhe: string) {
    super(`Captura de audio indisponivel: ${detalhe}`);
    this.name = "CapturaIndisponivelError";
  }
}

/* ------------------------------------------------------------------ puras */

/**
 * Reduz um quadro multicanal a mono pela media das amostras. Um canal so
 * passa direto (copia); canais de tamanhos diferentes nao acontecem no Web
 * Audio, mas indice faltante conta como silencio em vez de virar NaN.
 */
export function mediaCanais(canais: Float32Array[]): Float32Array {
  if (canais.length === 0) return new Float32Array(0);
  if (canais.length === 1) return Float32Array.from(canais[0]);
  const tamanho = canais[0].length;
  const saida = new Float32Array(tamanho);
  for (let i = 0; i < tamanho; i++) {
    let soma = 0;
    for (const canal of canais) soma += canal[i] ?? 0;
    saida[i] = soma / canais.length;
  }
  return saida;
}

/** Junta os blocos que o worklet foi entregando num PCM continuo unico. */
export function concatenarBlocos(blocos: Float32Array[]): Float32Array {
  const total = blocos.reduce((soma, b) => soma + b.length, 0);
  const saida = new Float32Array(total);
  let posicao = 0;
  for (const bloco of blocos) {
    saida.set(bloco, posicao);
    posicao += bloco.length;
  }
  return saida;
}

/**
 * Reamostra `amostras` de `taxaOrigem` para `taxaAlvo`.
 *
 * Razao INTEIRA (o caso real: contexto em 48 kHz -> 16 kHz, razao 3) decima
 * por media de blocos — a media e um passa-baixa rudimentar que segura o
 * aliasing da decimacao seca, suficiente para voz de comando. Razao
 * fracionaria (ex.: 44,1 kHz) cai na interpolacao linear, que tambem cobre o
 * caso taxaOrigem < taxaAlvo. Taxas iguais devolvem copia (nunca a mesma
 * referencia — quem chama pode mutar sem susto).
 */
export function reamostrar(
  amostras: Float32Array,
  taxaOrigem: number,
  taxaAlvo: number = TAXA_ALVO,
): Float32Array {
  if (amostras.length === 0 || taxaOrigem === taxaAlvo) {
    return Float32Array.from(amostras);
  }
  const razao = taxaOrigem / taxaAlvo;
  if (Number.isInteger(razao)) {
    const tamanho = Math.floor(amostras.length / razao);
    const saida = new Float32Array(tamanho);
    for (let i = 0; i < tamanho; i++) {
      let soma = 0;
      const inicio = i * razao;
      for (let j = 0; j < razao; j++) soma += amostras[inicio + j];
      saida[i] = soma / razao;
    }
    return saida;
  }
  const tamanho = Math.max(1, Math.floor(amostras.length / razao));
  const saida = new Float32Array(tamanho);
  for (let i = 0; i < tamanho; i++) {
    const posicao = i * razao;
    const inteiro = Math.floor(posicao);
    const fracao = posicao - inteiro;
    const a = amostras[inteiro] ?? 0;
    const b = inteiro + 1 < amostras.length ? amostras[inteiro + 1] : a;
    saida[i] = a + (b - a) * fracao;
  }
  return saida;
}

/** Duracao em segundos de um PCM na taxa dada — para log e diagnostico. */
export function duracaoSegundos(pcm: Float32Array, taxa: number = TAXA_ALVO): number {
  return pcm.length / taxa;
}

/** Maior amplitude absoluta do PCM — 0 significa silencio absoluto. */
export function picoAbsoluto(pcm: Float32Array): number {
  let pico = 0;
  for (const amostra of pcm) {
    const abs = Math.abs(amostra);
    if (abs > pico) pico = abs;
  }
  return pico;
}

/* ----------------------------------------------------------------- impura */

/** Uma captura em andamento. `parar` entrega o PCM; `cancelar` descarta tudo. */
export interface Captura {
  /** Fecha microfone e contexto e devolve o PCM 16 kHz mono acumulado. */
  parar(): Promise<Float32Array>;
  /** Fecha microfone e contexto descartando o audio. Idempotente. */
  cancelar(): void;
}

const NOME_PROCESSADOR = "captura-pcm-shogun";

/**
 * O processador roda DENTRO do AudioWorklet (thread de audio) e por isso vai
 * como texto, carregado via Blob URL — sem arquivo separado para o bundler
 * servir. Ele so copia os quadros brutos para a thread principal; toda a
 * matematica (mono, concatenacao, reamostragem) fica nas funcoes puras acima,
 * onde o vitest alcanca.
 */
const CODIGO_WORKLET = `
class CapturaPcm extends AudioWorkletProcessor {
  process(inputs) {
    const canais = inputs[0];
    if (canais && canais.length > 0 && canais[0].length > 0) {
      this.port.postMessage(canais.map((canal) => new Float32Array(canal)));
    }
    return true;
  }
}
registerProcessor("${NOME_PROCESSADOR}", CapturaPcm);
`;

function pararTrilhas(stream: MediaStream): void {
  for (const trilha of stream.getTracks()) trilha.stop();
}

/**
 * Abre o microfone e comeca a acumular PCM.
 *
 * As constraints pedem o pipeline de voz do Chromium (cancelamento de eco,
 * supressao de ruido, ganho automatico) — o eco residual do TTS morre aqui,
 * alem do `calar()` que o fluxo de ditado ja chama antes de abrir o mic.
 *
 * O `AudioContext` e pedido ja em 16 kHz: quando o WebView2 aceita, a
 * reamostragem vira copia; quando nao aceita (ou entrega outra taxa), a
 * `reamostrar` cobre a diferenca no `parar()`.
 */
export async function iniciarCaptura(): Promise<Captura> {
  const midia =
    typeof navigator !== "undefined" ? navigator.mediaDevices : undefined;
  if (!midia?.getUserMedia) {
    throw new CapturaIndisponivelError("getUserMedia ausente");
  }

  const stream = await midia.getUserMedia({
    audio: {
      channelCount: 1,
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    },
  });

  let contexto: AudioContext;
  try {
    contexto = new AudioContext({ sampleRate: TAXA_ALVO });
  } catch {
    // Taxa nao suportada pelo dispositivo/implementacao: fica a default
    // (tipicamente 48 kHz) e a reamostragem resolve.
    contexto = new AudioContext();
  }

  try {
    if (!contexto.audioWorklet) {
      throw new CapturaIndisponivelError("AudioWorklet ausente");
    }
    const url = URL.createObjectURL(
      new Blob([CODIGO_WORKLET], { type: "text/javascript" }),
    );
    try {
      await contexto.audioWorklet.addModule(url);
    } finally {
      URL.revokeObjectURL(url);
    }

    const origem = contexto.createMediaStreamSource(stream);
    // Sem saidas: o no so escuta — nada do microfone toca nos alto-falantes.
    const no = new AudioWorkletNode(contexto, NOME_PROCESSADOR, {
      numberOfOutputs: 0,
    });
    const blocos: Float32Array[] = [];
    no.port.onmessage = (evento: MessageEvent<Float32Array[]>) => {
      blocos.push(mediaCanais(evento.data));
    };
    origem.connect(no);

    const taxaReal = contexto.sampleRate;
    let encerrada = false;
    const desligar = () => {
      if (encerrada) return;
      encerrada = true;
      no.port.onmessage = null;
      try {
        origem.disconnect();
      } catch {
        // contexto ja fechado — nada a desligar
      }
      pararTrilhas(stream);
      void contexto.close().catch(() => {
        // fechar duas vezes nao e erro de quem gravou
      });
    };

    return {
      parar: async () => {
        desligar();
        return reamostrar(concatenarBlocos(blocos), taxaReal);
      },
      cancelar: desligar,
    };
  } catch (e) {
    // Falha depois do mic aberto: nao deixar trilha viva nem contexto orfao.
    pararTrilhas(stream);
    void contexto.close().catch(() => {});
    throw e;
  }
}
