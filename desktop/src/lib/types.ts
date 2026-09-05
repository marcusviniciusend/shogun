/**
 * Tipos do desktop.
 *
 * Os contratos do fio (`POST /comando`) NAO sao declarados aqui: vem de
 * `shared/ts`, que espelha os modelos Pydantic do servidor. Este arquivo so
 * reexporta, sob os nomes `*Wire` que o codigo do desktop ja usa, e acrescenta
 * o que e exclusivo da interface.
 *
 * O import e relativo e `import type` de proposito — ver "Como os clientes
 * consomem estes tipos" em `shared/README.md`.
 */

export type {
  AgentAction as AgentActionWire,
  CommandRequest as CommandRequestWire,
  CommandResponse as CommandResponseWire,
} from "../../../shared/ts";

/** Mensagem exibida no chat. Tipo de interface, nao trafega na rede. */
export interface MensagemChat {
  autor: "usuario" | "shogun";
  texto: string;
  /** Presente quando a mensagem e um erro de comunicacao, nao uma resposta. */
  erro?: boolean;
}
