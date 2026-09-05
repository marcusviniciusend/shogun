/**
 * Cliente HTTP do POST /comando e do GET /health.
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
  /** Causa crua, para log e diagnostico. Nao e mostrada ao usuario. */
  readonly causa?: unknown;

  constructor(mensagem: string, causa?: unknown) {
    super(mensagem);
    this.name = "ErroComando";
    this.causa = causa;
  }
}

/**
 * Traduz uma falha de rede do plugin numa frase util.
 *
 * O plugin devolve a mensagem do lado Rust (reqwest), que NAO e contrato
 * estavel: os textos podem mudar entre versoes. Por isso o reconhecimento e por
 * palavra-chave e o caso desconhecido cai num generico que carrega o texto
 * original — melhor mostrar algo bruto do que esconder a causa, que foi
 * exatamente o problema da versao anterior deste arquivo.
 */
function traduzirFalhaDeRede(erro: unknown, serverUrl: string): string {
  const texto = String(
    erro instanceof Error ? erro.message : erro,
  ).toLowerCase();

  const contem = (...termos: string[]) => termos.some((t) => texto.includes(t));

  // os error 10061 (Windows) / ECONNREFUSED: ninguem escutando na porta.
  if (contem("refused", "10061", "econnrefused", "trying to connect")) {
    return (
      `Nao ha servidor escutando em ${serverUrl}. ` +
      "Confira se ele esta rodando e se a URL nas configuracoes esta certa."
    );
  }

  if (contem("timed out", "timeout", "aborted", "os error 10060")) {
    return (
      `${serverUrl} aceitou a conexao mas nao respondeu a tempo. ` +
      "O servidor pode estar travado ou sobrecarregado."
    );
  }

  if (contem("dns", "resolve", "name or service", "nodename")) {
    return (
      `Nao consegui resolver o endereco de ${serverUrl}. ` +
      "Confira o nome do host nas configuracoes."
    );
  }

  // Rede fora, rota inexistente, TLS, VPN caida: nao da para nomear, entao
  // mostra o texto original em vez de engolir.
  return `Falha de rede ao falar com ${serverUrl}: ${String(erro)}`;
}

/** GET /health — barato, sem token e sem passar pelo LLM. */
export async function verificarSaude(config: Config): Promise<void> {
  // Limite proprio: sem ele, um servidor que aceita a conexao e nao responde
  // deixaria a verificacao pendurada e o indicador nunca sairia de
  // "verificando". Vale so para o /health; o POST /comando segue sem limite de
  // resposta (item 2 do levantamento, ainda em aberto).
  const cancelar = new AbortController();
  const limite = setTimeout(() => cancelar.abort(), 4000);

  let resposta: Response;
  try {
    resposta = await fetch(`${config.serverUrl}/health`, {
      method: "GET",
      signal: cancelar.signal,
    });
  } catch (e) {
    console.error("[shogun] /health falhou:", e);
    throw new ErroComando(traduzirFalhaDeRede(e, config.serverUrl), e);
  } finally {
    clearTimeout(limite);
  }

  if (!resposta.ok) {
    // Responde, mas nao como o Shogun responderia: outra aplicacao na porta,
    // ou um proxy no caminho.
    const msg =
      `${config.serverUrl} respondeu HTTP ${resposta.status} em /health. ` +
      "Pode haver outro programa ocupando essa porta.";
    console.error("[shogun] /health:", msg);
    throw new ErroComando(msg);
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
  } catch (e) {
    // A excecao crua vai para o console: e o unico lugar onde a causa real
    // sobrevive, e foi a falta dela que obrigou a diagnosticar com netstat.
    console.error("[shogun] POST /comando falhou:", e);
    throw new ErroComando(traduzirFalhaDeRede(e, config.serverUrl), e);
  }

  // Autenticacao chega como status HTTP, nao como excecao: o servidor
  // respondeu, so recusou.
  if (resposta.status === 401 || resposta.status === 403) {
    throw new ErroComando(
      config.token
        ? "O servidor recusou o token (HTTP " +
          resposta.status +
          "). Confira o token nas configuracoes."
        : "O servidor exige autenticacao e nenhum token esta configurado. " +
          "Preencha o SHOGUN_AUTH_TOKEN nas configuracoes.",
    );
  }
  if (resposta.status === 503) {
    throw new ErroComando(
      "O servidor esta de pe, mas o provedor de LLM esta indisponivel " +
        "no momento (503). Se o modelo local acabou de subir, ele pode estar " +
        "carregando — tente de novo em instantes.",
    );
  }
  if (!resposta.ok) {
    throw new ErroComando(
      `O servidor devolveu um erro inesperado (HTTP ${resposta.status}).`,
    );
  }

  try {
    return (await resposta.json()) as CommandResponseWire;
  } catch (e) {
    console.error("[shogun] resposta fora do formato:", e);
    throw new ErroComando(
      "O servidor devolveu uma resposta fora do formato esperado.",
      e,
    );
  }
}
