/**
 * Contratos do fio da API do Shogun (`POST /comando`).
 *
 * Nao sao declarados aqui: vem de `shared/ts`, que espelha os modelos Pydantic
 * do servidor. Este arquivo existe so para o resto do app importar de um lugar
 * curto, sem repetir o caminho relativo em cada tela.
 *
 * O import e relativo e `import type` de proposito — ver "Como os clientes
 * consomem estes tipos" em `shared/README.md`.
 */

export type {
  AgentAction,
  CommandRequest,
  CommandResponse,
} from "../../shared/ts";
