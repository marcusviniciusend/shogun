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

/**
 * Instrucao executavel que o servidor delega ao cliente.
 *
 * O servidor pode rodar em outra maquina e nao tem acesso ao SO do usuario;
 * quem executa e o cliente. `type` discrimina a instrucao (hoje so
 * `open_app`). Um cliente que nao suporta o alvo — no mobile so uma lista
 * curada de apps e viavel (`Linking.openURL` exige schemes declarados em
 * `LSApplicationQueriesSchemes`/`<queries>`) — nao executa nada e usa
 * `fallback_text` como resposta ao usuario.
 *
 * Regra de consumo (relacao com `CommandResponse.text`): o cliente tenta
 * executar ANTES de falar. Sucesso: fala `text`. Falha ou app nao suportado:
 * fala `fallback_text` EM VEZ de `text` — nunca os dois, senao o TTS anuncia
 * "Pedi para abrir o X" e se contradiz em seguida.
 *
 * Convencao para variantes futuros: todo novo `type` tambem carrega
 * `fallback_text`, para um cliente antigo sempre ter o que responder diante
 * de uma instrucao que nao reconhece.
 *
 * Invariante de seguranca: o servidor nunca envia URI, scheme ou comando
 * executavel — so o NOME do app. O mapeamento nome -> executavel/deep link e
 * sempre do cliente, entao o LLM nao consegue apontar para um alvo arbitrario.
 */
export interface ClientInstruction {
  type: "open_app";
  /**
   * Nome do aplicativo como o LLM interpretou (ex.: "Spotify"). O mapeamento
   * nome -> executavel/scheme e responsabilidade de cada cliente.
   */
  app: string;
  /**
   * Fala/exibicao quando o cliente nao consegue executar (app fora da lista
   * curada, falha ao abrir). Vem pronta do servidor, para o cliente nao ter
   * que redigir resposta nenhuma.
   */
  fallback_text: string;
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
  /**
   * Preenchida quando a acao pede execucao no aparelho do usuario. Clientes
   * que ainda nao executam instrucoes apenas exibem a action como metadado —
   * nunca interpretar `detail` (texto para humano) como instrucao.
   *
   * Com instruction preenchida, `status: "ok"` significa DELEGACAO FEITA, nao
   * app aberto: o historico da sessao registra ok mesmo que o cliente caia no
   * `fallback_text`. Divergencia aceitavel na v1; um eventual POST
   * /acao-resultado e extensao futura, nao pendencia deste contrato.
   */
  instruction?: ClientInstruction | null;
}
