/**
 * Ditado — o fluxo de push-to-talk por cima da captura (`lib/microfone.ts`):
 * segurar o botao grava, soltar transcreve, o texto entra no MESMO caminho da
 * mensagem digitada (`POST /comando`). Decisoes aprovadas em
 * docs/stt-desktop-design.md §5/§8.
 *
 * A COSTURA com o motor de STT e o tipo `Transcritor`: esta branch nao
 * conhece `lib/stt.ts` (branch paralela) — quem monta o app injeta a funcao.
 * A fiacao final (`import { transcrever } from "./lib/stt"`) e uma
 * micro-branch depois que as duas mergearem; ate la, o modo dev usa o
 * `transcritorDeDesenvolvimento` abaixo e o build de producao fica sem botao.
 *
 * Padrao dos modulos vizinhos (`falhas.ts`, `telas.ts`): quem DECIDE e este
 * modulo, coberto por vitest com dependencias injetadas; o componente so faz
 * fiacao de eventos e estado visual.
 */
import type { Captura } from "./microfone";
import {
  CapturaIndisponivelError,
  TAXA_ALVO,
  duracaoSegundos,
  picoAbsoluto,
} from "./microfone";

/**
 * A assinatura do motor de STT — o contrato da costura entre as branches.
 *
 * `pcm`: `Float32Array` mono a `TAXA_ALVO` (16 kHz), amostras em [-1, 1] —
 * exatamente o que `Captura.parar()` devolve. Devolve o texto transcrito
 * (vazio = nada reconhecido, nada e enviado); falha do motor deve virar
 * `throw`, que o fluxo mostra como erro local e volta ao ocioso.
 */
export type Transcritor = (pcm: Float32Array) => Promise<string>;

/**
 * Os tres estados visiveis do ditado (§5.2 do desenho): ocioso, gravando
 * (microfone ABERTO — indicador inequivoco na UI) e transcrevendo (mic ja
 * fechado, motor rodando). "Texto pronto" nao e estado: e o retorno ao ocioso
 * com o texto entregue ao fluxo de envio.
 */
export type EstadoDitado = "ocioso" | "gravando" | "transcrevendo";

/* ------------------------------------------------------------------ puras */

/**
 * So se comeca a gravar do ocioso, com o chat livre e o servidor alcancavel —
 * as mesmas condicoes que liberam o campo de texto. Gravar durante o proprio
 * envio criaria duas mensagens disputando o `carregando`.
 */
export function podeGravar(
  estado: EstadoDitado,
  chatCarregando: boolean,
  bloqueado: boolean,
): boolean {
  return estado === "ocioso" && !chatCarregando && !bloqueado;
}

/** Rotulo do botao de ditado (aria-label e title), por estado. */
export function rotuloBotao(estado: EstadoDitado): string {
  switch (estado) {
    case "gravando":
      return "Gravando — solte para enviar";
    case "transcrevendo":
      return "Transcrevendo…";
    default:
      return "Segurar para falar";
  }
}

/** Linha de status sob a entrada; `null` quando nao ha nada a dizer. */
export function statusDitado(estado: EstadoDitado): string | null {
  switch (estado) {
    case "gravando":
      return "Ouvindo — solte para enviar.";
    case "transcrevendo":
      return "Transcrevendo…";
    default:
      return null;
  }
}

/**
 * Traduz a falha de abertura do microfone para quem esta na tela. A recusa de
 * permissao aponta o caminho da chave de privacidade do Windows (§3.3 do
 * desenho): o tratamento e UX, nao codigo de permissao.
 */
export function mensagemErroCaptura(e: unknown): string {
  if (e instanceof CapturaIndisponivelError) {
    return "Este WebView não oferece captura de áudio — atualize o WebView2.";
  }
  const nome =
    typeof e === "object" && e !== null && "name" in e
      ? (e as { name: unknown }).name
      : null;
  switch (nome) {
    case "NotAllowedError":
    case "SecurityError":
      return (
        "Acesso ao microfone negado. Verifique Configurações do Windows → " +
        "Privacidade e segurança → Microfone."
      );
    case "NotFoundError":
    case "OverconstrainedError":
      return "Nenhum microfone encontrado.";
    case "NotReadableError":
      return "O microfone está em uso por outro aplicativo.";
    default:
      return "Não consegui acessar o microfone.";
  }
}

/** Texto vazio ou so espaco nao vira comando — devolve `null` para nao enviar. */
export function textoUtil(bruto: string): string | null {
  const limpo = bruto.trim();
  return limpo === "" ? null : limpo;
}

/* ------------------------------------------------------------- controlador */

/** O que o controlador precisa do mundo — tudo injetado, tudo mockavel. */
export interface DepsDitado {
  /** `calar` de `lib/voz.ts`: abrir o microfone SEMPRE cala o TTS (§5.3). */
  calar: () => void;
  /** `iniciarCaptura` de `lib/microfone.ts`. */
  iniciarCaptura: () => Promise<Captura>;
  /** O motor de STT injetado — a costura. */
  transcritor: Transcritor;
}

/** Callbacks para o componente refletir o fluxo na tela. */
export interface SinaisDitado {
  aoEstado: (estado: EstadoDitado) => void;
  /** Texto pronto para entrar no fluxo de envio (nunca vazio). */
  aoTexto: (texto: string) => void;
  /** Falha de captura ou de transcricao, ja traduzida para exibicao. */
  aoErro: (mensagem: string) => void;
}

export interface ControleDitado {
  /** Pressionou: cala o TTS e abre o microfone. No-op fora do ocioso. */
  iniciar(): Promise<void>;
  /** Soltou: fecha o mic, transcreve e entrega o texto. No-op sem gravacao. */
  parar(): Promise<void>;
  /** Aborta descartando o audio (ponteiro cancelado, troca de tela). */
  cancelar(): void;
}

/**
 * Cria o controlador de uma sessao de ditado. Um por componente basta: o
 * estado interno volta ao ocioso apos cada ciclo.
 *
 * A fase "abrindo" cobre a corrida real do push-to-talk: o `getUserMedia`
 * e assincrono (pode ate abrir prompt de permissao) e o usuario pode soltar
 * o botao antes de ele resolver. Soltar ou cancelar nesse intervalo DESCARTA
 * a captura — um toque rapido demais nao gravou nada que preste, e tratar
 * como desistencia evita mandar ruido de meio segundo para o motor.
 */
export function criarControleDitado(
  deps: DepsDitado,
  sinais: SinaisDitado,
): ControleDitado {
  type Fase = "ocioso" | "abrindo" | "gravando" | "transcrevendo";
  let fase: Fase = "ocioso";
  let captura: Captura | null = null;
  let desistiuAoAbrir = false;

  return {
    async iniciar() {
      if (fase !== "ocioso") return;
      fase = "abrindo";
      desistiuAoAbrir = false;
      // O eco morre por construcao: o Shogun cala ANTES de o mic abrir.
      deps.calar();
      let aberta: Captura;
      try {
        aberta = await deps.iniciarCaptura();
      } catch (e) {
        console.error("[shogun] abertura do microfone falhou:", e);
        fase = "ocioso";
        sinais.aoErro(mensagemErroCaptura(e));
        return;
      }
      if (desistiuAoAbrir) {
        aberta.cancelar();
        fase = "ocioso";
        return;
      }
      captura = aberta;
      fase = "gravando";
      sinais.aoEstado("gravando");
    },

    async parar() {
      if (fase === "abrindo") {
        desistiuAoAbrir = true;
        return;
      }
      if (fase !== "gravando" || captura === null) return;
      const gravacao = captura;
      captura = null;
      fase = "transcrevendo";
      sinais.aoEstado("transcrevendo");
      try {
        const pcm = await gravacao.parar();
        const texto = textoUtil(await deps.transcritor(pcm));
        if (texto !== null) sinais.aoTexto(texto);
      } catch (e) {
        console.error("[shogun] transcricao falhou:", e);
        sinais.aoErro("Não consegui transcrever o áudio.");
      } finally {
        fase = "ocioso";
        sinais.aoEstado("ocioso");
      }
    },

    cancelar() {
      if (fase === "abrindo") {
        desistiuAoAbrir = true;
        return;
      }
      if (fase !== "gravando" || captura === null) return;
      captura.cancelar();
      captura = null;
      fase = "ocioso";
      sinais.aoEstado("ocioso");
    },
  };
}

/* -------------------------------------------------------------------- dev */

/**
 * Transcritor provisorio do modo dev, enquanto a costura com `lib/stt.ts`
 * nao acontece: o audio capturado "morre num log" (branch 1 do desenho, §7).
 * Loga duracao e pico no console do WebView2 e devolve vazio — nada e
 * enviado ao servidor. NAO entra no build de producao (ver App.tsx).
 */
export const transcritorDeDesenvolvimento: Transcritor = async (pcm) => {
  const duracao = duracaoSegundos(pcm).toFixed(2);
  const pico = picoAbsoluto(pcm).toFixed(3);
  console.info(
    `[shogun] captura: ${pcm.length} amostras @ ${TAXA_ALVO} Hz ` +
      `(~${duracao}s), pico ${pico} — sem motor de STT nesta branch`,
  );
  return "";
};
