/**
 * Roteamento de falhas e politica de reenvio — logica de decisao extraida da
 * fiacao de `App.tsx` para teste, no mesmo padrao dos modulos vizinhos:
 * funcao pura exportada, coberta por vitest em ambiente node.
 *
 * O App continua dono da FIACAO (estado, refs, efeitos, chamadas de rede);
 * este modulo so DECIDE: para onde vai uma falha, quando ha reenvio e por
 * quanto tempo o refresh automatico pausa depois de um 429.
 */
import { ErroComando, ehErroDeConexao } from "./api";

/** Frase generica de quem nao e `ErroComando` — falha sem traducao propria. */
export function mensagemDeErro(e: unknown): string {
  return e instanceof ErroComando
    ? e.message
    : "Erro inesperado ao falar com o servidor.";
}

/**
 * Texto UNICO de problema de conexao, usado pelo chat e pelo painel de
 * Agentes. Os dois falham juntos quando o servidor cai; textos diferentes em
 * dois cantos da tela pareciam dois problemas. O detalhe (causa, URL) mora em
 * um lugar so: o banner do topo.
 */
export function mensagemServidorFora(): string {
  return "Sem conexão com o servidor — veja o aviso no topo.";
}

/** Resultado de `rotearFalha`: quem mostra o que. */
export interface FalhaRoteada {
  /**
   * Presente so quando a falha e de CONEXAO: o motivo detalhado que o banner
   * do topo exibe (o mesmo indicador que o /health alimenta). `null` para
   * erros especificos, que ficam onde ocorreram.
   */
  motivoBanner: string | null;
  /** O texto exibido no LOCAL da falha (bolha do chat, painel de Agentes). */
  textoLocal: string;
}

/**
 * Roteia uma falha para o lugar certo.
 *
 * Problema de CONEXAO vai para o indicador unico do topo e o local recebe so
 * a frase curta que aponta para la — chat e painel de Agentes falham juntos
 * quando o servidor cai, e este funil e o que impede a mesma queda de parecer
 * dois problemas. Erros especificos (auth, 503, formato) continuam onde
 * ocorreram.
 */
export function rotearFalha(e: unknown): FalhaRoteada {
  if (ehErroDeConexao(e)) {
    return { motivoBanner: e.message, textoLocal: mensagemServidorFora() };
  }
  return { motivoBanner: null, textoLocal: mensagemDeErro(e) };
}

/**
 * Espera antes do UNICO reenvio automatico de um 503: da tempo de o modelo
 * local terminar de carregar sem transformar o retry em martelada.
 */
export const ESPERA_REENVIO_MS = 2000;

/**
 * So o 503 (LLM indisponivel) ganha reenvio automatico — o caso do primeiro
 * comando do dia com o modelo local frio. Reenviar erro de auth ou de rede
 * nao muda nada e ainda esconderia o problema real; reenviar 429 e
 * exatamente o que o rate limit pune.
 */
export function deveReenviar(e: unknown): boolean {
  return e instanceof ErroComando && e.tipo === "llm_indisponivel";
}

/**
 * Executa `enviar` com UM reenvio automatico quando a falha passa em
 * `deveReenviar`, aguardando `esperar` entre as tentativas. Qualquer outra
 * falha — inclusive a da segunda tentativa — propaga intacta.
 */
export async function comReenvioUnico<T>(
  enviar: () => Promise<T>,
  esperar: () => Promise<void>,
): Promise<T> {
  try {
    return await enviar();
  } catch (e) {
    if (!deveReenviar(e)) throw e;
    await esperar();
    return await enviar();
  }
}

/**
 * Instante (ms) ate o qual o refresh AUTOMATICO do painel fica suspenso
 * depois de uma falha, honrando o Retry-After de um 429 — sem Retry-After,
 * um ciclo inteiro (`cicloMs`). Falha que nao e rate limit devolve `null`:
 * nenhuma pausa nova (a que existir segue valendo).
 */
export function pausaAposRateLimit(
  e: unknown,
  agora: number,
  cicloMs: number,
): number | null {
  if (e instanceof ErroComando && e.tipo === "rate_limit") {
    return agora + (e.retryAfterSegundos ?? cicloMs / 1000) * 1000;
  }
  return null;
}

/**
 * O tick automatico respeita a pausa do 429; o clique manual nao passa por
 * aqui — e uma acao deliberada do usuario e continua livre.
 */
export function refreshSuspenso(
  pausaAte: number | null,
  agora: number,
): boolean {
  return pausaAte !== null && agora < pausaAte;
}
