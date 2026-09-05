import { useEffect, useRef, useState } from "react";

import type { MensagemChat } from "../lib/types";

interface Props {
  mensagens: MensagemChat[];
  carregando: boolean;
  /** Servidor fora do ar: nao adianta deixar mandar. */
  bloqueado?: boolean;
  onEnviar: (texto: string) => void;
  onNovaConversa: () => void;
}

export function Chat({
  mensagens,
  carregando,
  bloqueado = false,
  onEnviar,
  onNovaConversa,
}: Props) {
  const [texto, setTexto] = useState("");
  const fimRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fimRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [mensagens, carregando]);

  function enviar(e: React.FormEvent) {
    e.preventDefault();
    const limpo = texto.trim();
    if (!limpo || carregando || bloqueado) return;
    setTexto("");
    onEnviar(limpo);
  }

  return (
    <section className="painel chat">
      <header className="painel-cabecalho">
        <h2>Conversa</h2>
        <button
          type="button"
          className="botao-secundario"
          onClick={onNovaConversa}
          disabled={carregando}
          title="Descarta a sessao atual e comeca uma conversa nova"
        >
          Nova conversa
        </button>
      </header>

      <div className="chat-historico">
        {mensagens.length === 0 && (
          <p className="chat-vazio">
            Digite um comando abaixo — por exemplo, "ver pendências dos agentes".
          </p>
        )}
        {mensagens.map((m, i) => (
          <div
            key={i}
            className={`chat-mensagem ${m.autor} ${m.erro ? "erro" : ""}`}
          >
            <span className="chat-autor">{m.autor === "usuario" ? "Você" : "Shogun"}</span>
            <p>{m.texto}</p>
          </div>
        ))}
        {carregando && (
          <div className="chat-mensagem shogun pensando">
            <span className="chat-autor">Shogun</span>
            <p>Pensando… (a primeira resposta pode demorar alguns segundos)</p>
          </div>
        )}
        <div ref={fimRef} />
      </div>

      <form className="chat-entrada" onSubmit={enviar}>
        <input
          type="text"
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          placeholder={
            bloqueado ? "Servidor não alcançado…" : "Digite um comando…"
          }
          disabled={carregando || bloqueado}
        />
        <button type="submit" disabled={carregando || bloqueado || !texto.trim()}>
          {carregando ? "Aguardando…" : "Enviar"}
        </button>
      </form>
    </section>
  );
}
