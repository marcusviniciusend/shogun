import type { AgentActionWire } from "../lib/types";

interface Props {
  acoes: AgentActionWire[];
  resumo: string | null;
  erro: string | null;
  carregando: boolean;
  onAtualizar: () => void;
}

/**
 * Painel de status dos agentes.
 *
 * Abordagem desta primeira versao: refresh MANUAL. O botao envia o comando
 * fixo "ver pendências dos agentes" ao /comando e exibe as `actions` da
 * resposta. Um polling periodico gastaria uma chamada de LLM por tick sem
 * ninguem olhando — quando existir um endpoint direto de pendencias (sem
 * passar pelo LLM), ai sim vale automatizar.
 */
export function PainelAgentes({ acoes, resumo, erro, carregando, onAtualizar }: Props) {
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

      {!erro && acoes.length === 0 && (
        <p className="agentes-vazio">
          Sem dados ainda. Clique em "Atualizar" para consultar as pendências.
        </p>
      )}

      {acoes.length > 0 && (
        <ul className="agentes-lista">
          {acoes.map((a, i) => (
            <li key={i} className={`agente ${a.status}`}>
              <span className="agente-status" aria-hidden>
                ●
              </span>
              <div>
                <strong>{a.agent}</strong>
                {a.detail && <p>{a.detail}</p>}
              </div>
            </li>
          ))}
        </ul>
      )}

      {resumo && <p className="agentes-resumo">{resumo}</p>}
    </section>
  );
}
