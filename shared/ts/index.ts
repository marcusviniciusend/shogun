/** Contratos compartilhados entre o servidor Shogun e os clientes. */

/** Mensagem enviada por um cliente ao servidor. */
export interface CommandRequest {
  /** Identificador da sessão de conversa. */
  sessionId: string;
  /** Texto já transcrito do comando de voz. */
  text: string;
  /** Origem do comando. */
  client: "desktop" | "mobile";
}

/** Resposta do servidor a um comando. */
export interface CommandResponse {
  sessionId: string;
  /** Texto a ser exibido e falado ao usuário. */
  text: string;
  /** Ações executadas por agentes durante o processamento. */
  actions: AgentAction[];
}

export interface AgentAction {
  agent: string;
  status: "ok" | "error";
  detail?: string;
}
