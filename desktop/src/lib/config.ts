/**
 * Configuracao persistida localmente via tauri-plugin-store.
 *
 * Nada de URL nem token no codigo: o default de URL existe so como
 * conveniencia de primeiro uso e e editavel na tela de configuracoes.
 * O arquivo fica no diretorio de dados do app (ex.: %APPDATA% no Windows).
 */
import { load, type Store } from "@tauri-apps/plugin-store";

/** Washi (claro, padrao), Sumi (escuro) ou o que o sistema pedir. */
export type Tema = "washi" | "sumi" | "sistema";

export interface Config {
  /** URL base do servidor, sem barra final. */
  serverUrl: string;
  /** Bearer token (SHOGUN_AUTH_TOKEN do servidor). Vazio = sem header. */
  token: string;
  tema: Tema;
}

export const CONFIG_DEFAULT: Config = {
  serverUrl: "http://localhost:8000",
  token: "",
  // Washi e o padrao: o desenho nasceu claro, o escuro e a alternativa.
  tema: "washi",
};

const TEMAS: Tema[] = ["washi", "sumi", "sistema"];

/**
 * Aplica o tema no elemento raiz.
 *
 * O CSS le `data-tema`; o "washi" nao escreve atributo nenhum, porque e o que
 * o `:root` ja define — assim o app abre no tema certo antes mesmo do JS rodar.
 */
/**
 * Qual tema esta valendo de fato — "sistema" vira washi ou sumi conforme o SO.
 *
 * Serve para escolher ASSET por tema (os videos do kanji sao renderizados um
 * para cada), coisa que CSS sozinho nao resolve.
 */
export function temaEfetivo(tema: Tema): "washi" | "sumi" {
  if (tema !== "sistema") return tema;
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "sumi"
    : "washi";
}

/**
 * Le o tema guardado e aplica ANTES do primeiro paint.
 *
 * Sem isso o app abriria em washi e trocaria para sumi um instante depois —
 * um flash branco na cara de quem escolheu escuro. Devolve o tema para quem
 * for montar a arvore ja saber com que cor comecar.
 */
export async function preCarregarTema(): Promise<Tema> {
  try {
    const { tema } = await carregarConfig();
    aplicarTema(tema);
    return tema;
  } catch {
    // Store inacessivel: abre no padrao, sem travar a inicializacao.
    return CONFIG_DEFAULT.tema;
  }
}

export function aplicarTema(tema: Tema): void {
  const raiz = document.documentElement;
  if (tema === "washi") {
    delete raiz.dataset.tema;
  } else {
    raiz.dataset.tema = tema;
  }
}

const ARQUIVO = "shogun.json";

let storePromise: Promise<Store> | null = null;

function store(): Promise<Store> {
  storePromise ??= load(ARQUIVO, { autoSave: true });
  return storePromise;
}

export async function carregarConfig(): Promise<Config> {
  const s = await store();
  const guardado = await s.get<string>("tema");
  return {
    serverUrl: (await s.get<string>("serverUrl")) ?? CONFIG_DEFAULT.serverUrl,
    token: (await s.get<string>("token")) ?? CONFIG_DEFAULT.token,
    // Valor invalido no store (versao antiga, edicao manual) cai no default
    // em vez de virar um `data-tema` que o CSS nao conhece.
    tema: TEMAS.includes(guardado as Tema)
      ? (guardado as Tema)
      : CONFIG_DEFAULT.tema,
  };
}

export async function salvarConfig(config: Config): Promise<void> {
  const s = await store();
  await s.set("serverUrl", config.serverUrl.replace(/\/+$/, ""));
  await s.set("token", config.token);
  await s.set("tema", config.tema);
}

/** Sessao de conversa corrente — persistida para sobreviver a reaberturas. */
export async function carregarSessionId(): Promise<string | null> {
  const s = await store();
  return (await s.get<string>("sessionId")) ?? null;
}

export async function salvarSessionId(sessionId: string | null): Promise<void> {
  const s = await store();
  if (sessionId === null) {
    await s.delete("sessionId");
  } else {
    await s.set("sessionId", sessionId);
  }
}
