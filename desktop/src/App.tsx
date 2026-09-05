import { useEffect, useState } from "react";

import indicadorUrl from "./assets/indicador-shogun.webm";
import { Chat } from "./components/Chat";
import { Configuracoes } from "./components/Configuracoes";
import { PainelAgentes } from "./components/PainelAgentes";
import { Sidebar, type View } from "./components/Sidebar";
import { Splash } from "./components/Splash";
import {
  StatusServidor,
  type EstadoServidor,
} from "./components/StatusServidor";
import { enviarComando, ErroComando, verificarSaude } from "./lib/api";
import {
  CONFIG_DEFAULT,
  carregarConfig,
  carregarSessionId,
  salvarConfig,
  salvarSessionId,
  type Config,
} from "./lib/config";
import type { AgentActionWire, MensagemChat } from "./lib/types";

import "./App.css";

const COMANDO_PENDENCIAS = "ver pendências dos agentes";

const REDUZ_MOVIMENTO = window.matchMedia(
  "(prefers-reduced-motion: reduce)",
).matches;

function mensagemDeErro(e: unknown): string {
  return e instanceof ErroComando ? e.message : "Erro inesperado ao falar com o servidor.";
}

/** Texto exibido quando o /health barrou o envio. O detalhe fica no banner. */
function mensagemServidorFora(): string {
  return "Não enviei: o servidor não está respondendo. Veja o aviso no topo.";
}

export default function App() {
  const [config, setConfig] = useState<Config>(CONFIG_DEFAULT);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [view, setView] = useState<View>("chat");
  // Chat e agentes lado a lado — toggle proprio na sidebar (ver Sidebar.tsx).
  const [dividido, setDividido] = useState(false);

  const [mensagens, setMensagens] = useState<MensagemChat[]>([]);
  const [chatCarregando, setChatCarregando] = useState(false);

  const [acoesAgentes, setAcoesAgentes] = useState<AgentActionWire[]>([]);
  const [resumoAgentes, setResumoAgentes] = useState<string | null>(null);
  const [erroAgentes, setErroAgentes] = useState<string | null>(null);
  const [agentesCarregando, setAgentesCarregando] = useState(false);

  const [estadoServidor, setEstadoServidor] =
    useState<EstadoServidor>("verificando");
  const [motivoServidor, setMotivoServidor] = useState<string | null>(null);

  // Splash roda uma vez por abertura; quem pediu menos movimento nao o ve.
  const [splashAtivo, setSplashAtivo] = useState(!REDUZ_MOVIMENTO);
  // O kanji do wordmark e escrito em loop continuo; com reducao de
  // movimento, fica o glifo estatico.
  const animaMarca = !REDUZ_MOVIMENTO;

  /**
   * Pergunta ao /health se da para falar com o servidor.
   *
   * Devolve o resultado alem de guardar no estado, para quem chama poder
   * decidir na hora sem esperar o re-render.
   */
  async function checarSaude(alvo: Config): Promise<boolean> {
    setEstadoServidor("verificando");
    try {
      await verificarSaude(alvo);
      setEstadoServidor("ok");
      setMotivoServidor(null);
      return true;
    } catch (e) {
      setEstadoServidor("inalcancavel");
      setMotivoServidor(mensagemDeErro(e));
      return false;
    }
  }

  useEffect(() => {
    (async () => {
      const guardada = await carregarConfig();
      setConfig(guardada);
      setSessionId(await carregarSessionId());
      return guardada;
    })()
      .catch(() => {
        // Store inacessivel: segue com os defaults em memoria.
        return CONFIG_DEFAULT;
      })
      .then(checarSaude);
  }, []);

  async function atualizarSessao(novoId: string) {
    setSessionId(novoId);
    await salvarSessionId(novoId);
  }

  async function enviarMensagem(texto: string) {
    setMensagens((m) => [...m, { autor: "usuario", texto }]);
    if (!(await checarSaude(config))) {
      // Barra antes de gastar uma chamada de LLM num servidor que nao responde.
      setMensagens((m) => [
        ...m,
        { autor: "shogun", texto: mensagemServidorFora(), erro: true },
      ]);
      return;
    }
    setChatCarregando(true);
    try {
      const resposta = await enviarComando(config, texto, sessionId);
      await atualizarSessao(resposta.session_id);
      setMensagens((m) => [...m, { autor: "shogun", texto: resposta.text }]);
      // Se o comando digitado tambem consultou pendencias, aproveita no painel.
      if (resposta.actions.length > 0) {
        setAcoesAgentes(resposta.actions);
        setErroAgentes(null);
      }
    } catch (e) {
      setMensagens((m) => [...m, { autor: "shogun", texto: mensagemDeErro(e), erro: true }]);
    } finally {
      setChatCarregando(false);
    }
  }

  async function atualizarAgentes() {
    setAgentesCarregando(true);
    setErroAgentes(null);
    if (!(await checarSaude(config))) {
      setErroAgentes(mensagemServidorFora());
      setAgentesCarregando(false);
      return;
    }
    try {
      const resposta = await enviarComando(config, COMANDO_PENDENCIAS, sessionId);
      await atualizarSessao(resposta.session_id);
      setAcoesAgentes(resposta.actions);
      setResumoAgentes(resposta.text);
    } catch (e) {
      setErroAgentes(mensagemDeErro(e));
    } finally {
      setAgentesCarregando(false);
    }
  }

  async function novaConversa() {
    setMensagens([]);
    setSessionId(null);
    await salvarSessionId(null);
  }

  async function salvar(nova: Config) {
    setConfig(nova);
    await salvarConfig(nova);
    // URL ou token novos: o estado anterior nao diz mais nada sobre este alvo.
    await checarSaude(nova);
  }

  const mostraChat = view === "chat" || (dividido && view !== "config");
  const mostraAgentes = view === "agentes" || (dividido && view !== "config");

  return (
    <div className="app">
      <Sidebar
        view={view}
        dividido={dividido}
        onNovaConversa={() => {
          void novaConversa();
          setView(dividido ? view : "chat");
        }}
        onVer={(v) => {
          setView(v);
          if (v !== "config") setDividido(false);
        }}
        onAlternarDividido={() => {
          setDividido((d) => !d);
          if (view === "config") setView("chat");
        }}
      />
      <header className="app-cabecalho">
        <h1>
          <span className="marca-kanji-wrap" aria-hidden>
            <span className={`marca-kanji${animaMarca ? " oculto" : ""}`}>
              将軍
            </span>
            {animaMarca && (
              <video
                className="marca-kanji-video"
                src={indicadorUrl}
                autoPlay
                loop
                muted
                playsInline
              />
            )}
          </span>
          <span className="marca-nome">Shogun</span>
        </h1>
      </header>

      <StatusServidor
        estado={estadoServidor}
        motivo={motivoServidor}
        onVerificar={() => void checarSaude(config)}
      />

      {view === "config" ? (
        <Configuracoes
          config={config}
          onSalvar={salvar}
          onFechar={() => setView("chat")}
        />
      ) : (
        <main className={`dashboard${dividido ? " dividido" : ""}`}>
          {mostraChat && (
            <Chat
              mensagens={mensagens}
              carregando={chatCarregando}
              bloqueado={estadoServidor === "inalcancavel"}
              onEnviar={enviarMensagem}
            />
          )}
          {mostraAgentes && (
            <PainelAgentes
              acoes={acoesAgentes}
              resumo={resumoAgentes}
              erro={erroAgentes}
              carregando={agentesCarregando}
              onAtualizar={atualizarAgentes}
            />
          )}
        </main>
      )}

      {splashAtivo && <Splash onFim={() => setSplashAtivo(false)} />}
    </div>
  );
}
