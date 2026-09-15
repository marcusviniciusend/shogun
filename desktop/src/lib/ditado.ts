/**
 * Ditado — o fluxo de push-to-talk: segurar o botao grava, soltar transcreve,
 * o texto entra no MESMO caminho da mensagem digitada (`POST /comando`).
 * Decisoes aprovadas em docs/stt-desktop-design.md §5/§8.
 *
 * A maquina de estados (`ocioso → gravando → transcrevendo`, com a fase
 * interna `abrindo` para a corrida do push-to-talk) sobreviveu inteira a
 * troca da captura. O que mudou foi so o que ela aciona: antes um objeto
 * `Captura` do `lib/microfone.ts` (getUserMedia + AudioWorklet no WebView2),
 * agora os comandos Tauri de `lib/stt.ts` — o microfone e o whisper vivem no
 * mesmo processo Rust e o PCM nunca chega ate aqui.
 *
 * Padrao dos modulos vizinhos (`falhas.ts`, `telas.ts`): quem DECIDE e este
 * modulo, coberto por vitest com dependencias injetadas; o componente so faz
 * fiacao de eventos e estado visual. As deps continuam injetadas — e o que
 * mantem estes testes livres de mock do Tauri.
 */

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
      return "Gravando — clique para enviar";
    case "transcrevendo":
      return "Transcrevendo…";
    default:
      return "Clique para falar";
  }
}

/** Linha de status sob a entrada; `null` quando nao ha nada a dizer. */
export function statusDitado(estado: EstadoDitado): string | null {
  switch (estado) {
    case "gravando":
      return "Ouvindo — clique para enviar.";
    case "transcrevendo":
      return "Transcrevendo…";
    default:
      return null;
  }
}

/**
 * Uma falha do ciclo, ja pronta para a tela.
 *
 * `modeloAusente` sai separado do texto de proposito: esse caso NAO e um erro
 * comum, e o gatilho da oferta de download do modelo (~466 MB). A UI precisa
 * distinguir "deu errado, tente de novo" de "falta baixar o motor" sem ler a
 * mensagem.
 */
export interface FalhaDitado {
  mensagem: string;
  modeloAusente: boolean;
}

/**
 * A forma minima de um erro vindo do Rust (`ErroStt` de `lib/stt.ts`).
 *
 * Reconhecida por pato, e nao por `instanceof`, para que este modulo nao
 * importe `lib/stt.ts` — importa-lo arrastaria `@tauri-apps/api` para dentro
 * de todo teste de ditado, e a injecao de dependencias existe justamente para
 * evitar isso.
 */
function erroDoMotor(e: unknown): { tipo: string; mensagem: string } | null {
  if (typeof e !== "object" || e === null) return null;
  const { tipo, message } = e as { tipo?: unknown; message?: unknown };
  if (typeof tipo !== "string" || typeof message !== "string") return null;
  return { tipo, mensagem: message };
}

/**
 * Traduz a falha do ciclo para quem esta na tela.
 *
 * O Rust ja devolve mensagem exibivel (portugues, sem caminho de disco, e
 * apontando a chave de privacidade do Windows quando o caso e permissao
 * negada) — repetir esse texto aqui seria manter duas versoes da mesma
 * frase. Entao o funil e: erro do motor usa a mensagem dele; qualquer outra
 * coisa (falha de IPC, bug de fiacao) cai na frase generica recebida.
 */
export function mensagemErroDitado(e: unknown, generica: string): FalhaDitado {
  const erro = erroDoMotor(e);
  if (erro === null) return { mensagem: generica, modeloAusente: false };
  return {
    mensagem: erro.mensagem,
    modeloAusente: erro.tipo === "modelo_ausente",
  };
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
  /** `iniciarGravacao` de `lib/stt.ts`: abre o microfone no Rust. */
  iniciarGravacao: () => Promise<unknown>;
  /**
   * `pararGravacaoETranscrever` de `lib/stt.ts`: fecha o microfone e devolve
   * a fala ja transcrita. Um passo so porque o PCM nao existe deste lado.
   */
  pararETranscrever: () => Promise<string>;
  /** `cancelarGravacao` de `lib/stt.ts`: fecha descartando o audio. */
  cancelarGravacao: () => void;
}

/** Callbacks para o componente refletir o fluxo na tela. */
export interface SinaisDitado {
  aoEstado: (estado: EstadoDitado) => void;
  /** Texto pronto para entrar no fluxo de envio (nunca vazio). */
  aoTexto: (texto: string) => void;
  /** Falha de captura ou de transcricao, ja traduzida para exibicao. */
  aoErro: (falha: FalhaDitado) => void;
}

export interface ControleDitado {
  /** Primeiro clique: cala o TTS e abre o microfone. No-op fora do ocioso. */
  iniciar(): Promise<void>;
  /** Segundo clique: fecha o mic, transcreve e entrega. No-op sem gravacao. */
  parar(): Promise<void>;
  /** Aborta descartando o audio (troca de tela, nova conversa, desmontagem). */
  cancelar(): void;
}

/**
 * Cria o controlador de uma sessao de ditado. Um por componente basta: o
 * estado interno volta ao ocioso apos cada ciclo.
 *
 * O ciclo e ALTERNADO, nao push-to-talk: um clique abre o microfone e ele
 * fica aberto ate o clique seguinte. Segurar o botao cansa em ditado longo e
 * prende o ponteiro numa janela que o usuario pode querer usar enquanto fala;
 * alternar tambem entrega de graca o teclado, porque um <button> com onClick
 * ja responde a espaco e enter sem handler nenhum.
 *
 * A fase "abrindo" cobre a corrida que sobrevive a troca: abrir o dispositivo
 * e assincrono (o cpal negocia formato com o WASAPI) e o usuario pode desistir
 * antes de ele resolver. `parar` ou `cancelar` nesse intervalo DESCARTA a
 * captura — chamando `cancelarGravacao`, porque o dispositivo JA abriu do lado
 * Rust e ficaria aberto se ninguem o fechasse.
 */
export function criarControleDitado(
  deps: DepsDitado,
  sinais: SinaisDitado,
): ControleDitado {
  type Fase = "ocioso" | "abrindo" | "gravando" | "transcrevendo";
  let fase: Fase = "ocioso";
  let desistiuAoAbrir = false;

  return {
    async iniciar() {
      if (fase !== "ocioso") return;
      fase = "abrindo";
      desistiuAoAbrir = false;
      // O eco morre por construcao: o Shogun cala ANTES de o mic abrir.
      deps.calar();
      try {
        await deps.iniciarGravacao();
      } catch (e) {
        console.error("[shogun] abertura do microfone falhou:", e);
        fase = "ocioso";
        sinais.aoErro(mensagemErroDitado(e, "Não consegui acessar o microfone."));
        return;
      }
      if (desistiuAoAbrir) {
        deps.cancelarGravacao();
        fase = "ocioso";
        return;
      }
      fase = "gravando";
      sinais.aoEstado("gravando");
    },

    async parar() {
      if (fase === "abrindo") {
        desistiuAoAbrir = true;
        return;
      }
      if (fase !== "gravando") return;
      fase = "transcrevendo";
      sinais.aoEstado("transcrevendo");
      try {
        const texto = textoUtil(await deps.pararETranscrever());
        if (texto !== null) sinais.aoTexto(texto);
      } catch (e) {
        console.error("[shogun] transcricao falhou:", e);
        sinais.aoErro(mensagemErroDitado(e, "Não consegui transcrever o áudio."));
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
      if (fase !== "gravando") return;
      deps.cancelarGravacao();
      fase = "ocioso";
      sinais.aoEstado("ocioso");
    },
  };
}
