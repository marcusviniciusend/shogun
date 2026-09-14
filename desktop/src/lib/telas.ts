/**
 * Decisoes de navegacao e de conteudo das telas — logica pura extraida da
 * fiacao de `App.tsx` para teste, no mesmo padrao dos modulos vizinhos.
 *
 * O import do tipo `View` e type-only de proposito: some na compilacao e
 * nao arrasta o componente Sidebar (JSX) para os testes em ambiente node.
 */
import type { View } from "../components/Sidebar";
import type { SessaoResumoWire } from "./types";

/** O que o dashboard mostra para uma combinacao de view + dividido. */
export interface Visibilidade {
  chat: boolean;
  agentes: boolean;
  conversas: boolean;
}

/**
 * O dividido so junta chat + agentes; conversas e uma tela propria e config
 * nem passa pelo dashboard (o App troca o <main> inteiro pela tela de
 * configuracoes).
 */
export function visibilidade(view: View, dividido: boolean): Visibilidade {
  const emDashboard = view === "chat" || view === "agentes";
  return {
    chat: view === "chat" || (dividido && emDashboard),
    agentes: view === "agentes" || (dividido && emDashboard),
    conversas: view === "conversas",
  };
}

/**
 * Navegar pela sidebar desfaz o dividido — exceto para config, que e um
 * parenteses: fechar a tela de configuracoes volta ao layout que estava.
 */
export function divididoAposVer(destino: View, dividido: boolean): boolean {
  return destino === "config" ? dividido : false;
}

/**
 * Dividido e sempre chat + agentes: alternar vindo de outra tela aterra no
 * chat; dentro do dashboard, a view fica onde esta.
 */
export function viewAposAlternarDividido(view: View): View {
  return view === "config" || view === "conversas" ? "chat" : view;
}

/**
 * Nova conversa com o dashboard dividido nao muda de tela (o chat ja esta
 * visivel); fora do dividido, aterra no chat.
 */
export function viewAposNovaConversa(view: View, dividido: boolean): View {
  return dividido ? view : "chat";
}

/**
 * Lista de conversas: mais recentemente ativa primeiro. A comparacao e
 * lexicografica de proposito — `atualizada_em` e ISO 8601 sem fuso
 * (docs/DATABASE.md), e comparar o texto evita criar Date so para ordenar.
 * Nao muta a lista recebida.
 */
export function ordenarSessoes(
  sessoes: SessaoResumoWire[],
): SessaoResumoWire[] {
  return [...sessoes].sort((a, b) =>
    b.atualizada_em.localeCompare(a.atualizada_em),
  );
}
