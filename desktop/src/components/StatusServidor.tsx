export type EstadoServidor = "verificando" | "ok" | "inalcancavel";

interface Props {
  estado: EstadoServidor;
  motivo: string | null;
  onVerificar: () => void;
}

/**
 * Faixa de status da conexao com o servidor.
 *
 * Existe para o app parar de descobrir que o servidor esta fora so depois de
 * gastar uma chamada de LLM inteira. O /health responde em ~1,5 ms, sem token e
 * sem tocar no modelo.
 *
 * Silenciosa quando esta tudo certo: banner permanente vira ruido.
 */
export function StatusServidor({ estado, motivo, onVerificar }: Props) {
  if (estado === "ok") return null;

  if (estado === "verificando") {
    return (
      <div className="banner-servidor verificando" role="status">
        <span>Verificando o servidor…</span>
      </div>
    );
  }

  return (
    <div className="banner-servidor inalcancavel" role="alert">
      <div>
        <strong>Servidor não alcançado.</strong>
        {motivo && <p>{motivo}</p>}
      </div>
      <button type="button" className="botao-secundario" onClick={onVerificar}>
        Verificar de novo
      </button>
    </div>
  );
}
