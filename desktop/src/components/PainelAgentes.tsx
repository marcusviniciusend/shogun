import type { PendenciaWire } from "../lib/types";

interface Props {
  pendencias: PendenciaWire[];
  total: number;
  erro: string | null;
  carregando: boolean;
  /** Ultima atualizacao bem-sucedida, para o refresh automatico ser legivel. */
  atualizadoEm: Date | null;
  onAtualizar: () => void;
}

/** Status que significam "algo travando": ganham o bengara. */
export const STATUS_CRITICOS = new Set(["travado", "erro"]);

/**
 * Painel de pendencias dos agentes.
 *
 * Consome o GET /pendencias (leitura direta, sem LLM): por isso o refresh
 * automatico periodico ficou barato — antes, cada atualizacao custava uma
 * chamada de modelo via POST /comando. O botao Atualizar continua para quem
 * nao quer esperar o proximo tick.
 */
export function PainelAgentes({
  pendencias,
  total,
  erro,
  carregando,
  atualizadoEm,
  onAtualizar,
}: Props) {
  return (
    <section className="painel agentes">
      <header className="painel-cabecalho">
        <h2>Agentes</h2>
        <button
          type="button"
          className="botao-secundario"
          onClick={onAtualizar}
          disabled={carregando}
        >
          {carregando ? "Consultando…" : "Atualizar"}
        </button>
      </header>

      {erro && <p className="aviso-erro">{erro}</p>}

      {!erro && atualizadoEm !== null && pendencias.length === 0 && (
        <p className="agentes-vazio">Nenhuma pendência aberta.</p>
      )}

      {!erro && atualizadoEm === null && pendencias.length === 0 && (
        <p className="agentes-vazio">Consultando as pendências…</p>
      )}

      {pendencias.length > 0 && (
        <ul className="agentes-lista">
          {pendencias.map((p, i) => (
            <li
              key={`${p.agente_id}-${i}`}
              className={`agente ${
                STATUS_CRITICOS.has(p.status) ? "error" : "ok"
              }`}
            >
              <span className="agente-status" aria-hidden>
                ●
              </span>
              <div>
                <strong>{p.agente_nome}</strong>
                <p>
                  {p.descricao}
                  <span className="agente-detalhe"> — {p.status}</span>
                </p>
              </div>
            </li>
          ))}
        </ul>
      )}

      {atualizadoEm !== null && (
        <p className="agentes-resumo">
          {total} {total === 1 ? "pendência aberta" : "pendências abertas"} ·
          atualizado às{" "}
          {atualizadoEm.toLocaleTimeString("pt-BR", {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
          })}
        </p>
      )}
    </section>
  );
}
