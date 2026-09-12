import type { SessaoResumoWire } from "../lib/types";

interface Props {
  sessoes: SessaoResumoWire[];
  /** Conversa aberta no chat agora — marcada na lista. */
  sessionIdAtual: string | null;
  erro: string | null;
  carregando: boolean;
  onAtualizar: () => void;
  onAbrir: (id: string) => void;
}

/**
 * Data curta para a lista: hoje vira hora, resto vira dia/mes.
 *
 * O servidor grava UTC sem tzinfo (docs/DATABASE.md); o sufixo Z faz o
 * Date interpretar como UTC e exibir no fuso local.
 */
export function quando(iso: string): string {
  const data = new Date(iso.endsWith("Z") ? iso : `${iso}Z`);
  if (Number.isNaN(data.getTime())) return "";
  const hoje = new Date();
  const mesmoDia =
    data.getDate() === hoje.getDate() &&
    data.getMonth() === hoje.getMonth() &&
    data.getFullYear() === hoje.getFullYear();
  return mesmoDia
    ? data.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })
    : data.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
}

/**
 * Lista de conversas anteriores (GET /sessoes). Abrir uma carrega o
 * historico e o chat passa a conversar NAQUELA sessao — e o antidoto do
 * "assunto antigo vazou": a conversa eterna vira historico navegavel.
 */
export function Conversas({
  sessoes,
  sessionIdAtual,
  erro,
  carregando,
  onAtualizar,
  onAbrir,
}: Props) {
  return (
    <section className="painel conversas">
      <header className="painel-cabecalho">
        <h2>Conversas</h2>
        <button
          type="button"
          className="botao-secundario"
          onClick={onAtualizar}
          disabled={carregando}
        >
          {carregando ? "Carregando…" : "Atualizar"}
        </button>
      </header>

      {erro && <p className="aviso-erro">{erro}</p>}

      {!erro && !carregando && sessoes.length === 0 && (
        <p className="conversas-vazio">
          Nenhuma conversa guardada ainda — a primeira mensagem cria uma.
        </p>
      )}

      {sessoes.length > 0 && (
        <ul className="conversas-lista">
          {sessoes.map((s) => (
            <li key={s.id}>
              <button
                type="button"
                className={`conversa-item${
                  s.id === sessionIdAtual ? " atual" : ""
                }`}
                onClick={() => onAbrir(s.id)}
              >
                <span className="conversa-titulo">
                  {s.titulo || "(sem título)"}
                </span>
                <span className="conversa-meta">
                  {quando(s.atualizada_em)} · {s.total_mensagens}{" "}
                  {s.total_mensagens === 1 ? "mensagem" : "mensagens"}
                  {s.id === sessionIdAtual && " · atual"}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
