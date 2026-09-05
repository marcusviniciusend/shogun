/**
 * Tipos do fio da API do Shogun (`POST /comando`).
 *
 * Fonte da verdade: `shared/python/__init__.py` — o servidor serializa os
 * modelos Pydantic em snake_case, entao e snake_case que trafega no JSON.
 * (`shared/ts/index.ts` descreve os mesmos campos em camelCase; enquanto a
 * divergencia nao for resolvida no shared, o cliente segue o formato real.)
 */

export interface CommandRequest {
  /** Nulo na primeira mensagem: o servidor cria a sessao e devolve o id. */
  session_id?: string | null;
  /** Texto ja transcrito do comando. */
  text: string;
  /** Origem do comando. */
  client: "desktop" | "mobile";
}

export interface AgentAction {
  agent: string;
  status: "ok" | "error";
  detail?: string | null;
}

export interface CommandResponse {
  /** Sempre preenchido — inclusive quando o request veio sem id. */
  session_id: string;
  /** Texto a ser exibido e falado ao usuario. */
  text: string;
  actions: AgentAction[];
}
