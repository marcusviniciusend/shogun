/**
 * Contratos compartilhados entre o servidor Shogun e os clientes.
 *
 * Os nomes de campo sao exatamente os que trafegam no JSON — `snake_case`,
 * como o servidor emite. Os modelos Pydantic em `shared/python` nao usam
 * alias, entao `session_id` e `session_id` na rede.
 *
 * Estes tipos descrevem o **fio**, nao o estilo do codigo do cliente. Um
 * cliente pode chamar a variavel de `sessionId` internamente; o que ele nao
 * pode e esperar `sessionId` no corpo da resposta.
 */

/** Mensagem enviada por um cliente ao servidor. */
export interface CommandRequest {
  /**
   * Identificador da sessao de conversa.
   *
   * Nulo (ou ausente) na primeira mensagem: o servidor cria a sessao e devolve
   * o id em `CommandResponse.session_id`, que o cliente guarda e reenvia
   * depois.
   */
  session_id?: string | null;
  /** Texto ja transcrito do comando de voz. */
  text: string;
  /** Origem do comando. */
  client: "desktop" | "mobile";
}

/** Resposta do servidor a um comando. */
export interface CommandResponse {
  /** Sempre preenchido — inclusive quando o request veio sem id. */
  session_id: string;
  /** Texto a ser exibido e falado ao usuario. */
  text: string;
  /** Acoes executadas por agentes durante o processamento. */
  actions: AgentAction[];
}

export interface AgentAction {
  agent: string;
  status: "ok" | "error";
  /**
   * `null` quando a acao nao tem detalhe — nao ausente. O Pydantic declara
   * `detail: str | None = None` e serializa a chave mesmo vazia, o que o
   * OpenAPI do servidor confirma: `detail: ["string", "null"]`.
   */
  detail?: string | null;
}
