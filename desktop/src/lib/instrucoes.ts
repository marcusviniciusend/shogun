/**
 * Execucao das ClientInstruction delegadas pelo servidor (hoje so `open_app`).
 *
 * Invariante de seguranca do contrato (`shared/ts`): o servidor manda so o
 * NOME do app; executavel, args e URI saem SEMPRE do mapa curado abaixo — e o
 * escopo do tauri-plugin-shell em `capabilities/default.json` fixa executavel
 * e args por comando nomeado, entao nem este codigo consegue rodar outra
 * coisa. String vinda do servidor nunca chega ao spawn. (Licao do incidente
 * do escopo http: a permissao no capabilities e parte da feature, nao
 * detalhe.)
 *
 * Regra de consumo (docstring de `ClientInstruction`): tentar executar ANTES
 * de exibir/falar. Sucesso -> `CommandResponse.text`; falha, app fora do mapa
 * ou `type` desconhecido -> `fallback_text` EM VEZ de `text`, nunca os dois.
 */
import { Command } from "@tauri-apps/plugin-shell";

import type { ClientInstructionWire, CommandResponseWire } from "./types";

/**
 * Mapa curado nome -> comando do escopo shell. Pequeno de proposito;
 * configuravel fica para depois. Windows-first: `explorer.exe` cobre URL
 * (navegador padrao), pasta (gerenciador de arquivos) e URI `spotify:` —
 * se o Spotify nao estiver instalado, o proprio Windows avisa.
 *
 * Cada entrada nomeia um comando de `capabilities/default.json`; os args
 * daqui tem que bater com os de la, senao o Tauri recusa o spawn.
 */
export const APPS_CURADOS: Record<string, { comando: string; args: string[] }> = {
  navegador: { comando: "abrir-navegador", args: ["https://www.google.com"] },
  explorer: { comando: "abrir-explorer", args: [] },
  calculadora: { comando: "abrir-calculadora", args: [] },
  spotify: { comando: "abrir-spotify", args: ["spotify:"] },
};

/** Sinonimos que o LLM costuma mandar, ja na forma normalizada. */
const SINONIMOS: Record<string, keyof typeof APPS_CURADOS> = {
  browser: "navegador",
  chrome: "navegador",
  internet: "navegador",
  arquivos: "explorer",
  "explorador de arquivos": "explorer",
  "gerenciador de arquivos": "explorer",
  calc: "calculadora",
};

/**
 * Normaliza o nome vindo do LLM para a chave do mapa: minusculas, sem
 * acentos, espacos colapsados. "Calculadora " e "calculadora" sao o mesmo
 * pedido.
 */
export function normalizar(nome: string): string {
  return nome
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * Tenta abrir o app do mapa curado. `true` = spawn aceito pelo Tauri.
 *
 * `spawn` (e nao `execute`): abrir app e disparar-e-esquecer, e o
 * `explorer.exe` devolve codigo de saida diferente de zero mesmo quando abre
 * — esperar o processo so geraria falso negativo.
 */
async function abrirApp(nome: string): Promise<boolean> {
  const chave = normalizar(nome);
  const alvo = APPS_CURADOS[chave] ?? APPS_CURADOS[SINONIMOS[chave] ?? ""];
  if (!alvo) {
    console.warn(`[shogun] open_app: "${nome}" fora do mapa curado.`);
    return false;
  }
  try {
    await Command.create(alvo.comando, alvo.args).spawn();
    return true;
  } catch (e) {
    // Permissao recusada, executavel ausente: registra a causa e cai no
    // fallback_text — nunca quebra o fluxo da resposta.
    console.error(`[shogun] open_app "${nome}" falhou:`, e);
    return false;
  }
}

/**
 * Executa as instrucoes da resposta e devolve o texto a exibir/falar.
 *
 * Sem instrucao, devolve `text` como sempre. Com instrucao, aplica a regra de
 * consumo do contrato. `type` desconhecido (cliente antigo diante de servidor
 * novo) cai no `fallback_text` — a convencao do contrato garante que ele
 * sempre existe.
 */
export async function executarInstrucoes(
  resposta: CommandResponseWire,
): Promise<string> {
  const instrucao: ClientInstructionWire | null | undefined =
    resposta.actions.find((a) => a.instruction != null)?.instruction;

  if (instrucao == null) return resposta.text;
  if (instrucao.type !== "open_app") return instrucao.fallback_text;

  return (await abrirApp(instrucao.app)) ? resposta.text : instrucao.fallback_text;
}
