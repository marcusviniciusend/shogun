import { useEffect, useRef, useState } from "react";

import samuraiSprite from "../assets/samurai-run7.png";
import type { MensagemChat } from "../lib/types";

/**
 * Selo do Shogun — o 将 carimbado ao lado da fala dele.
 *
 * Substitui o rotulo "Shogun" escrito por extenso: quem fala se reconhece pelo
 * selo, nao por uma etiqueta. O nome continua no `aria-label`, para quem le por
 * leitor de tela.
 */
function Selo() {
  return (
    <span className="chat-selo" role="img" aria-label="Shogun">
      将
    </span>
  );
}

interface Props {
  mensagens: MensagemChat[];
  carregando: boolean;
  /** Servidor fora do ar: nao adianta deixar mandar. */
  bloqueado?: boolean;
  onEnviar: (texto: string) => void;
}

export function Chat({
  mensagens,
  carregando,
  bloqueado = false,
  onEnviar,
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
            {m.autor === "usuario" ? (
              <span className="chat-autor">Você</span>
            ) : (
              <Selo />
            )}
            <p>{m.texto}</p>
          </div>
        ))}
        {carregando && (
          <div className="chat-mensagem shogun pensando">
            <Selo />
            {/*
              O samurai correndo no lugar de "Pensando…" escrito. Sprite de 7
              quadros animado por `steps(7)` — sem JS, sem timer.
            */}
            <div className="pensando-linha">
              <span
                className="samurai"
                role="img"
                aria-label="samurai correndo"
                style={{ backgroundImage: `url(${samuraiSprite})` }}
              />
              <span className="pensando-texto">
                Pensando… (a primeira resposta pode demorar alguns segundos)
              </span>
            </div>
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
