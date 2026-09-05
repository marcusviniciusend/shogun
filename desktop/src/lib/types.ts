/**
 * Tipos do fio (wire) do POST /comando.
 *
 * Atencao: `shared/ts/index.ts` declara os contratos em camelCase
 * (`sessionId`), mas o JSON real emitido pelo servidor (Pydantic, sem alias)
 * e snake_case (`session_id`). Ate o contrato compartilhado ser alinhado ao
 * fio, o desktop usa estes tipos locais, que espelham o JSON de verdade.
 */

export interface CommandRequestWire {
  /** Nulo na primeira mensagem: o servidor cria a sessao e devolve o id. */
  session_id: string | null;
  text: string;
  client: "desktop";
}

export interface AgentActionWire {
  agent: string;
  status: "ok" | "error";
  detail?: string | null;
}

export interface CommandResponseWire {
  session_id: string;
  text: string;
  actions: AgentActionWire[];
}

/** Mensagem exibida no chat. */
export interface MensagemChat {
  autor: "usuario" | "shogun";
  texto: string;
  /** Presente quando a mensagem e um erro de comunicacao, nao uma resposta. */
  erro?: boolean;
}
