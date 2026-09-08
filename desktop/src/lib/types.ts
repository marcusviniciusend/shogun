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
  ClientInstruction as ClientInstructionWire,
  CommandRequest as CommandRequestWire,
  CommandResponse as CommandResponseWire,
} from "../../../shared/ts";

/*
 * Shapes combinados na rodada 5 (GET /sessoes, GET /sessoes/{id}/mensagens,
 * GET /pendencias). Contratos ainda so do servidor — quando estabilizarem,
 * promover a `shared/` nas duas pontas, como o proprio servidor documenta.
 */

/** Resumo de uma conversa em GET /sessoes. */
export interface SessaoResumoWire {
  id: string;
  criada_em: string;
  atualizada_em: string;
  titulo: string;
  total_mensagens: number;
}

export interface SessoesResponseWire {
  total: number;
  sessoes: SessaoResumoWire[];
}

/** Uma fala do historico em GET /sessoes/{id}/mensagens. */
export interface MensagemHistoricoWire {
  autor: "usuario" | "shogun";
  texto: string;
  criada_em: string;
}

export interface MensagensResponseWire {
  session_id: string;
  mensagens: MensagemHistoricoWire[];
}

/** Pendencia de GET /pendencias — espelha `Pendencia` do dominio do servidor. */
export interface PendenciaWire {
  agente_id: string;
  agente_nome: string;
  status: "executando" | "pendente" | "travado" | "erro" | "concluido";
  descricao: string;
  timestamp: string;
  prioridade: number;
}

export interface PendenciasResponseWire {
  total: number;
  pendencias: PendenciaWire[];
}

/** Mensagem exibida no chat. Tipo de interface, nao trafega na rede. */
export interface MensagemChat {
  autor: "usuario" | "shogun";
  texto: string;
  /** Presente quando a mensagem e um erro de comunicacao, nao uma resposta. */
  erro?: boolean;
  /**
   * O comando que falhou, guardado na propria bolha de erro: e o que o botao
   * "Tentar de novo" reenvia sem o usuario redigitar.
   */
  reenvio?: string;
}
