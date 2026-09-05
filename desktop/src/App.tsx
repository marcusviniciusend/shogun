import { useEffect, useState } from "react";

import { Chat } from "./components/Chat";
import { Configuracoes } from "./components/Configuracoes";
import { PainelAgentes } from "./components/PainelAgentes";
import { enviarComando, ErroComando } from "./lib/api";
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

  useEffect(() => {
    (async () => {
      setConfig(await carregarConfig());
      setSessionId(await carregarSessionId());
    })().catch(() => {
      // Store inacessivel: segue com os defaults em memoria.
    });
  }, []);

  async function atualizarSessao(novoId: string) {
    setSessionId(novoId);
    await salvarSessionId(novoId);
  }

  async function enviarMensagem(texto: string) {
    setMensagens((m) => [...m, { autor: "usuario", texto }]);
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
  }

  return (
    <div className="app">
      <header className="app-cabecalho">
        <h1>Shogun</h1>
        <button
          type="button"
          className="botao-secundario"
          onClick={() => setTelaConfig((v) => !v)}
        >
          {telaConfig ? "Dashboard" : "Configurações"}
        </button>
      </header>

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
