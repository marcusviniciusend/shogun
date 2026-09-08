/**
 * Voz do Shogun — TTS via speechSynthesis nativo do WebView2.
 *
 * Zero dependencia e zero chave de API: a voz vem do proprio Windows. Voz
 * natural (Piper/API) fica como upgrade futuro atras desta mesma interface —
 * quem chama so conhece `falar`/`calar`.
 *
 * O que se fala e o texto FINAL exibido na bolha do chat — depois do funil
 * `executarInstrucoes` (sucesso fala `text`, falha fala `fallback_text`).
 * Erros de conexao e o painel de agentes NAO passam por aqui.
 */

/** `speechSynthesis` pode nao existir (webview antigo, testes). */
function sintetizador(): SpeechSynthesis | null {
  return typeof window !== "undefined" && "speechSynthesis" in window
    ? window.speechSynthesis
    : null;
}

let vozEscolhida: SpeechSynthesisVoice | null = null;

/**
 * Escolhe a melhor voz disponivel: pt-BR primeiro, depois qualquer pt.
 * Sem nenhuma, fica `null` e o utterance sai na voz default do sistema —
 * fallback gracioso, nunca erro.
 */
function escolherVoz(vozes: SpeechSynthesisVoice[]): void {
  const norm = (lang: string) => lang.toLowerCase().replace("_", "-");
  vozEscolhida =
    vozes.find((v) => norm(v.lang) === "pt-br") ??
    vozes.find((v) => norm(v.lang).startsWith("pt")) ??
    null;
}

/**
 * Prepara a selecao de voz. Chamar uma vez na montagem do app.
 *
 * No WebView2 `getVoices()` costuma devolver lista VAZIA ate o motor
 * carregar; a lista real chega no evento `voiceschanged`. Trata os dois
 * momentos — e re-escolhe se o sistema ganhar/perder vozes depois.
 */
export function inicializarVozes(): void {
  const sintese = sintetizador();
  if (!sintese) return;
  escolherVoz(sintese.getVoices());
  sintese.addEventListener("voiceschanged", () => {
    escolherVoz(sintese.getVoices());
  });
}

/**
 * Fala `texto`, cancelando qualquer fala anterior — resposta nova cala a
 * antiga; nada de fila de falas sobrepostas.
 */
export function falar(texto: string): void {
  const sintese = sintetizador();
  if (!sintese || !texto.trim()) return;

  sintese.cancel();

  const fala = new SpeechSynthesisUtterance(texto);
  // `lang` sempre pt-BR, mesmo sem voz pt instalada: o motor tenta a
  // pronuncia certa com o que tiver.
  fala.lang = "pt-BR";
  if (vozEscolhida) fala.voice = vozEscolhida;
  sintese.speak(fala);
}

/** Interrompe a fala em curso, se houver. Idempotente. */
export function calar(): void {
  sintetizador()?.cancel();
}
