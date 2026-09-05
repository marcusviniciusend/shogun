/**
 * Configuracao persistida localmente via tauri-plugin-store.
 *
 * Nada de URL nem token no codigo: o default de URL existe so como
 * conveniencia de primeiro uso e e editavel na tela de configuracoes.
 * O arquivo fica no diretorio de dados do app (ex.: %APPDATA% no Windows).
 */
import { load, type Store } from "@tauri-apps/plugin-store";

export interface Config {
  /** URL base do servidor, sem barra final. */
  serverUrl: string;
  /** Bearer token (SHOGUN_AUTH_TOKEN do servidor). Vazio = sem header. */
  token: string;
}

export const CONFIG_DEFAULT: Config = {
  serverUrl: "http://localhost:8000",
  token: "",
};

const ARQUIVO = "shogun.json";

let storePromise: Promise<Store> | null = null;

function store(): Promise<Store> {
  storePromise ??= load(ARQUIVO, { autoSave: true });
  return storePromise;
}

export async function carregarConfig(): Promise<Config> {
  const s = await store();
  return {
    serverUrl: (await s.get<string>("serverUrl")) ?? CONFIG_DEFAULT.serverUrl,
    token: (await s.get<string>("token")) ?? CONFIG_DEFAULT.token,
  };
}

export async function salvarConfig(config: Config): Promise<void> {
  const s = await store();
  await s.set("serverUrl", config.serverUrl.replace(/\/+$/, ""));
  await s.set("token", config.token);
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
