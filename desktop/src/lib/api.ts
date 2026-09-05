/**
 * Cliente HTTP do POST /comando.
 *
 * Usa o fetch do tauri-plugin-http (via Rust), nao o do webview: assim nao ha
 * CORS e o servidor nao precisa de SHOGUN_ALLOWED_ORIGINS, seja em
 * localhost ou num IP Tailscale.
 */
import { fetch } from "@tauri-apps/plugin-http";

import type { Config } from "./config";
import type { CommandRequestWire, CommandResponseWire } from "./types";

/** Erro ja traduzido para mensagem exibivel ao usuario. */
export class ErroComando extends Error {
  constructor(mensagem: string) {
    super(mensagem);
    this.name = "ErroComando";
  }
}

export async function enviarComando(
  config: Config,
  texto: string,
  sessionId: string | null,
): Promise<CommandResponseWire> {
  const corpo: CommandRequestWire = {
    session_id: sessionId,
    text: texto,
    client: "desktop",
  };

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (config.token) {
    headers.Authorization = `Bearer ${config.token}`;
  }

  let resposta: Response;
  try {
    resposta = await fetch(`${config.serverUrl}/comando`, {
      method: "POST",
      headers,
      body: JSON.stringify(corpo),
    });
  } catch {
    throw new ErroComando(
      `Servidor nao respondeu em ${config.serverUrl}. ` +
        "Confira se ele esta rodando e se a URL nas configuracoes esta certa.",
    );
  }

  if (resposta.status === 401 || resposta.status === 403) {
    throw new ErroComando(
      "Autenticacao recusada (token invalido ou ausente). " +
        "Confira o token nas configuracoes.",
    );
  }
  if (resposta.status === 503) {
    throw new ErroComando(
      "O servidor esta de pe, mas o provedor de LLM esta indisponivel " +
        "no momento (503). Tente de novo em instantes.",
    );
  }
  if (!resposta.ok) {
    throw new ErroComando(
      `O servidor devolveu um erro inesperado (HTTP ${resposta.status}).`,
    );
  }

  try {
    return (await resposta.json()) as CommandResponseWire;
  } catch {
    throw new ErroComando("O servidor devolveu uma resposta fora do formato esperado.");
  }
}
