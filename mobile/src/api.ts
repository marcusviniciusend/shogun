/**
 * Cliente HTTP da API do Shogun.
 *
 * Toda falha vira `ApiError` com uma mensagem pronta para a interface — as
 * telas nao precisam distinguir fetch que rejeitou de status HTTP de erro.
 */

import { CommandRequest, CommandResponse } from "./contracts";
import { ConfigServidor, normalizarUrl } from "./storage";

/** O LLM pode demorar (modelo local frio, fallback); folga sobre os 30s do servidor. */
const TIMEOUT_MS = 60_000;

export class ApiError extends Error {
  constructor(mensagem: string, readonly status?: number) {
    super(mensagem);
    this.name = "ApiError";
  }
}

function exigirConfig(config: ConfigServidor): string {
  const url = normalizarUrl(config.url);
  if (!url) {
    throw new ApiError(
      "Configure a URL do servidor na aba Config (IP Tailscale do PC)."
    );
  }
  return url;
}

async function requisitar(
  url: string,
  init: RequestInit
): Promise<Response> {
  const controlador = new AbortController();
  const timer = setTimeout(() => controlador.abort(), TIMEOUT_MS);
  try {
    return await fetch(url, { ...init, signal: controlador.signal });
  } catch (erro) {
    if (erro instanceof Error && erro.name === "AbortError") {
      throw new ApiError("O servidor demorou demais para responder.");
    }
    throw new ApiError(
      "Nao consegui falar com o servidor. Confira a URL e se o Tailscale esta ativo nos dois lados."
    );
  } finally {
    clearTimeout(timer);
  }
}

/** `GET /health` — nao exige token; serve para testar a conexao na tela Config. */
export async function verificarSaude(config: ConfigServidor): Promise<void> {
  const base = exigirConfig(config);
  const resposta = await requisitar(`${base}/health`, { method: "GET" });
  if (!resposta.ok) {
    throw new ApiError(
      `O servidor respondeu, mas com erro (HTTP ${resposta.status}).`,
      resposta.status
    );
  }
}

/** `POST /comando` — envia o texto e devolve a resposta interpretada. */
export async function enviarComando(
  config: ConfigServidor,
  sessionId: string | null,
  texto: string
): Promise<CommandResponse> {
  const base = exigirConfig(config);
  const corpo: CommandRequest = {
    session_id: sessionId,
    text: texto,
    client: "mobile",
  };

  const resposta = await requisitar(`${base}/comando`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(config.token ? { Authorization: `Bearer ${config.token}` } : {}),
    },
    body: JSON.stringify(corpo),
  });

  if (resposta.status === 401 || resposta.status === 403) {
    throw new ApiError(
      "O servidor recusou o token. Confira o SHOGUN_AUTH_TOKEN na aba Config.",
      resposta.status
    );
  }
  if (resposta.status === 503) {
    throw new ApiError(
      "O Shogun esta sem acesso ao modelo agora. Tente de novo em instantes.",
      503
    );
  }
  if (!resposta.ok) {
    throw new ApiError(`Erro do servidor (HTTP ${resposta.status}).`, resposta.status);
  }

  try {
    return (await resposta.json()) as CommandResponse;
  } catch {
    throw new ApiError("O servidor devolveu uma resposta fora do formato esperado.");
  }
}
