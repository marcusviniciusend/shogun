import { useEffect, useState } from "react";

import { Chat } from "./components/Chat";
import { Configuracoes } from "./components/Configuracoes";
import { PainelAgentes } from "./components/PainelAgentes";
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
  const [telaConfig, setTelaConfig] = useState(false);

  const [mensagens, setMensagens] = useState<MensagemChat[]>([]);
  const [chatCarregando, setChatCarregando] = useState(false);

  const [acoesAgentes, setAcoesAgentes] = useState<AgentActionWire[]>([]);
  const [resumoAgentes, setResumoAgentes] = useState<string | null>(null);
  const [erroAgentes, setErroAgentes] = useState<string | null>(null);
  const [agentesCarregando, setAgentesCarregando] = useState(false);

  const [estadoServidor, setEstadoServidor] =
    useState<EstadoServidor>("verificando");
  const [motivoServidor, setMotivoServidor] = useState<string | null>(null);

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

  return (
    <div className="app">
      <header className="app-cabecalho">
        <h1>
          <span
            className={`marca-kanji${chatCarregando || agentesCarregando ? " pensando" : ""}`}
            aria-hidden
          >
            将軍
          </span>
          <span className="marca-nome">Shogun</span>
        </h1>
        <button
          type="button"
          className="botao-secundario"
          onClick={() => setTelaConfig((v) => !v)}
        >
          {telaConfig ? "Dashboard" : "Configurações"}
        </button>
      </header>

      <StatusServidor
        estado={estadoServidor}
        motivo={motivoServidor}
        onVerificar={() => void checarSaude(config)}
      />

      {telaConfig ? (
        <Configuracoes
          config={config}
          onSalvar={salvar}
          onFechar={() => setTelaConfig(false)}
        />
      ) : (
        <main className="dashboard">
          <Chat
            mensagens={mensagens}
            carregando={chatCarregando}
            bloqueado={estadoServidor === "inalcancavel"}
            onEnviar={enviarMensagem}
            onNovaConversa={novaConversa}
          />
          <PainelAgentes
            acoes={acoesAgentes}
            resumo={resumoAgentes}
            erro={erroAgentes}
            carregando={agentesCarregando}
            onAtualizar={atualizarAgentes}
          />
        </main>
      )}
    </div>
  );
}
