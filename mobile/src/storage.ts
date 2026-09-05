/**
 * Persistencia local do app — configuracao do servidor e ids de sessao.
 *
 * Tudo via AsyncStorage: nada de URL ou token hardcoded. O token fica no
 * aparelho do usuario e so sai daqui no header Authorization.
 */

import AsyncStorage from "@react-native-async-storage/async-storage";

const CHAVE_URL = "shogun/serverUrl";
const CHAVE_TOKEN = "shogun/authToken";
const CHAVE_SESSAO_CHAT = "shogun/chatSessionId";
const CHAVE_SESSAO_STATUS = "shogun/statusSessionId";

export interface ConfigServidor {
  /** Ex.: http://100.101.102.103:8000 (IP Tailscale do PC). */
  url: string;
  token: string;
}

/** Remove barra final para concatenar caminhos sem gerar `//comando`. */
export function normalizarUrl(url: string): string {
  return url.trim().replace(/\/+$/, "");
}

export async function carregarConfig(): Promise<ConfigServidor> {
  const [url, token] = await AsyncStorage.multiGet([CHAVE_URL, CHAVE_TOKEN]);
  return { url: url[1] ?? "", token: token[1] ?? "" };
}

export async function salvarConfig(config: ConfigServidor): Promise<void> {
  await AsyncStorage.multiSet([
    [CHAVE_URL, normalizarUrl(config.url)],
    [CHAVE_TOKEN, config.token.trim()],
  ]);
}

/**
 * Sessoes separadas por tela: o chat conversa numa sessao continua; a tela de
 * status manda sempre o mesmo comando e nao deve poluir o historico do chat.
 */
export async function carregarSessao(
  tela: "chat" | "status"
): Promise<string | null> {
  return AsyncStorage.getItem(
    tela === "chat" ? CHAVE_SESSAO_CHAT : CHAVE_SESSAO_STATUS
  );
}

export async function salvarSessao(
  tela: "chat" | "status",
  sessionId: string
): Promise<void> {
  await AsyncStorage.setItem(
    tela === "chat" ? CHAVE_SESSAO_CHAT : CHAVE_SESSAO_STATUS,
    sessionId
  );
}
