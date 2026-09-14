import { useEffect, useMemo, useRef, useState } from "react";

import samuraiSprite from "../assets/samurai-run7.png";
import {
  criarControleDitado,
  podeGravar,
  rotuloBotao,
  statusDitado,
  type EstadoDitado,
} from "../lib/ditado";
import {
  cancelarGravacao,
  iniciarGravacao,
  pararGravacaoETranscrever,
} from "../lib/stt";
import type { MensagemChat } from "../lib/types";
import { calar } from "../lib/voz";

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
  /** Reenvia o comando guardado na bolha de erro de indice `indice`. */
  onReenviar: (indice: number, texto: string) => void;
  /**
   * Ha motor de voz neste ambiente (ver `sttDisponivel` em `lib/stt.ts`)?
   * FALSO = sem botao de falar — o chat continua o de sempre. E o gate do
   * push-to-talk: capacidade detectada em runtime, e nao flag de build.
   */
  ditadoDisponivel?: boolean;
}

export function Chat({
  mensagens,
  carregando,
  bloqueado = false,
  onEnviar,
  onReenviar,
  ditadoDisponivel = false,
}: Props) {
  const [texto, setTexto] = useState("");
  const fimRef = useRef<HTMLDivElement>(null);

  // ---- ditado (push-to-talk). Toda a decisao vive em lib/ditado.ts; aqui e
  // so fiacao de eventos de ponteiro/teclado para o controlador.
  const [estadoDitado, setEstadoDitado] = useState<EstadoDitado>("ocioso");
  const [erroDitado, setErroDitado] = useState<string | null>(null);
  // `onEnviar` muda a cada render do App; o controlador e criado uma vez —
  // a ref garante que o texto transcrito caia sempre no handler atual.
  const enviarRef = useRef(onEnviar);
  enviarRef.current = onEnviar;
  const controle = useMemo(
    () =>
      ditadoDisponivel
        ? criarControleDitado(
            {
              calar,
              iniciarGravacao,
              pararETranscrever: () => pararGravacaoETranscrever(),
              // `cancelarGravacao` nunca rejeita; o `void` so descarta a
              // promise, porque cancelar e limpeza e nao tem retorno util.
              cancelarGravacao: () => void cancelarGravacao(),
            },
            {
              aoEstado: setEstadoDitado,
              // O texto transcrito entra NO MESMO fluxo da mensagem digitada.
              aoTexto: (t) => enviarRef.current(t),
              aoErro: (falha) => setErroDitado(falha.mensagem),
            },
          )
        : null,
    [ditadoDisponivel],
  );
  // Desmontar no meio de uma gravacao nao pode deixar microfone aberto.
  useEffect(() => () => controle?.cancelar(), [controle]);

  function pressionarFalar() {
    if (!controle || !podeGravar(estadoDitado, carregando, bloqueado)) return;
    setErroDitado(null);
    void controle.iniciar();
  }

  function soltarFalar() {
    void controle?.parar();
  }

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
            <div>
              <p>{m.texto}</p>
              {m.erro && m.reenvio != null && (
                <button
                  type="button"
                  className="botao-secundario chat-tentar"
                  onClick={() => onReenviar(i, m.reenvio!)}
                  disabled={carregando}
                >
                  Tentar de novo
                </button>
              )}
            </div>
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
        {controle && (
          /*
            Push-to-talk: segurar grava, soltar transcreve e envia. Os eventos
            de ponteiro cobrem mouse e toque; o par keydown/keyup cobre teclado
            (segurar espaco). O capture prende o pointerup mesmo se o cursor
            sair do botao antes de soltar.
          */
          <button
            type="button"
            className={`chat-falar${
              estadoDitado !== "ocioso" ? ` ${estadoDitado}` : ""
            }`}
            aria-label={rotuloBotao(estadoDitado)}
            title={rotuloBotao(estadoDitado)}
            aria-pressed={estadoDitado === "gravando"}
            disabled={
              estadoDitado === "transcrevendo" ||
              (estadoDitado === "ocioso" && (carregando || bloqueado))
            }
            onPointerDown={(e) => {
              // So botao principal; preventDefault mantem o foco no input.
              if (e.button !== 0) return;
              e.preventDefault();
              e.currentTarget.setPointerCapture(e.pointerId);
              pressionarFalar();
            }}
            onPointerUp={() => soltarFalar()}
            onPointerCancel={() => controle.cancelar()}
            onKeyDown={(e) => {
              if ((e.key === " " || e.key === "Enter") && !e.repeat) {
                e.preventDefault();
                pressionarFalar();
              }
            }}
            onKeyUp={(e) => {
              if (e.key === " " || e.key === "Enter") {
                e.preventDefault();
                soltarFalar();
              }
            }}
          >
            <span aria-hidden>声</span>
          </button>
        )}
        <button type="submit" disabled={carregando || bloqueado || !texto.trim()}>
          {carregando ? "Aguardando…" : "Enviar"}
        </button>
      </form>
      {controle && (statusDitado(estadoDitado) !== null || erroDitado) && (
        <p
          className={`chat-ditado-status${
            erroDitado && estadoDitado === "ocioso" ? " erro" : ""
          }`}
          role="status"
        >
          {statusDitado(estadoDitado) ?? erroDitado}
        </p>
      )}
    </section>
  );
}
