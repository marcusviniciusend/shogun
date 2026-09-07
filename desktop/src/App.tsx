import { useEffect, useState } from "react";

import indicadorSumi from "./assets/indicador-sumi.webm";
import indicadorWashi from "./assets/indicador-washi.webm";
import { Chat } from "./components/Chat";
import { Configuracoes } from "./components/Configuracoes";
import { PainelAgentes } from "./components/PainelAgentes";
import { Sidebar, type View } from "./components/Sidebar";
import { Splash } from "./components/Splash";
import {
  StatusServidor,
  type EstadoServidor,
} from "./components/StatusServidor";
import {
  ehErroDeConexao,
  enviarComando,
  ErroComando,
  verificarSaude,
} from "./lib/api";
import { executarInstrucoes } from "./lib/instrucoes";
import {
  CONFIG_DEFAULT,
  aplicarTema,
  carregarConfig,
  temaEfetivo,
  carregarSessionId,
  salvarConfig,
  salvarSessionId,
  type Config,
  type Tema,
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

/**
 * Texto UNICO de problema de conexao, usado pelo chat e pelo painel de
 * Agentes. Os dois falham juntos quando o servidor cai; textos diferentes em
 * dois cantos da tela pareciam dois problemas. O detalhe (causa, URL) mora em
 * um lugar so: o banner do topo.
 */
function mensagemServidorFora(): string {
  return "Sem conexão com o servidor — veja o aviso no topo.";
}

/**
 * Espera antes do UNICO reenvio automatico de um 503: da tempo de o modelo
 * local terminar de carregar sem transformar o retry em martelada.
 */
const ESPERA_REENVIO_MS = 2000;

interface Props {
  /** Tema ja lido do store antes do primeiro paint (ver main.tsx). */
  temaInicial: Tema;
}

export default function App({ temaInicial }: Props) {
  const [config, setConfig] = useState<Config>({
    ...CONFIG_DEFAULT,
    tema: temaInicial,
  });
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
      aplicarTema(guardada.tema);
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

  /**
   * `enviarComando` com UM reenvio automatico quando o erro e 503 (LLM
   * indisponivel) — o caso do primeiro comando do dia com o modelo local
   * frio. So esse tipo: reenviar erro de auth ou de rede nao muda nada e
   * ainda esconderia o problema real.
   */
  async function chamarComReenvio(texto: string) {
    try {
      return await enviarComando(config, texto, sessionId);
    } catch (e) {
      if (!(e instanceof ErroComando) || e.tipo !== "llm_indisponivel") {
        throw e;
      }
      await new Promise((r) => setTimeout(r, ESPERA_REENVIO_MS));
      return await enviarComando(config, texto, sessionId);
    }
  }

  /**
   * Roteia uma falha para o lugar certo e devolve o texto a exibir no local.
   *
   * Problema de CONEXAO vai para o indicador unico do topo (o mesmo que o
   * /health alimenta) e o local recebe so a frase curta que aponta para la —
   * chat e painel de Agentes falham juntos quando o servidor cai, e este
   * funil e o que impede a mesma queda de parecer dois problemas. Erros
   * especificos (auth, 503, formato) continuam onde ocorreram.
   */
  function registrarFalha(e: unknown): string {
    if (ehErroDeConexao(e)) {
      setEstadoServidor("inalcancavel");
      setMotivoServidor(e.message);
      return mensagemServidorFora();
    }
    return mensagemDeErro(e);
  }

  /** Envia `texto` ao servidor. A bolha do usuario ja esta no historico. */
  async function processarComando(texto: string) {
    if (!(await checarSaude(config))) {
      // Barra antes de gastar uma chamada de LLM num servidor que nao
      // responde. A bolha guarda o comando: volta o servidor, um clique reenvia.
      setMensagens((m) => [
        ...m,
        { autor: "shogun", texto: mensagemServidorFora(), erro: true, reenvio: texto },
      ]);
      return;
    }
    setChatCarregando(true);
    try {
      const resposta = await chamarComReenvio(texto);
      await atualizarSessao(resposta.session_id);
      // Instrucao delegada (ex.: open_app) executa ANTES de exibir: sucesso
      // mostra o text do servidor, falha mostra o fallback_text — nunca os dois.
      const textoFinal = await executarInstrucoes(resposta);
      setMensagens((m) => [...m, { autor: "shogun", texto: textoFinal }]);
      // Se o comando digitado tambem consultou pendencias, aproveita no painel.
      if (resposta.actions.length > 0) {
        setAcoesAgentes(resposta.actions);
        setErroAgentes(null);
      }
    } catch (e) {
      setMensagens((m) => [
        ...m,
        { autor: "shogun", texto: registrarFalha(e), erro: true, reenvio: texto },
      ]);
    } finally {
      setChatCarregando(false);
    }
  }

  async function enviarMensagem(texto: string) {
    setMensagens((m) => [...m, { autor: "usuario", texto }]);
    await processarComando(texto);
  }

  /**
   * "Tentar de novo" de uma bolha de erro: remove a bolha clicada e reenvia o
   * comando que ela guardou. A mensagem original do usuario segue no
   * historico — nada e redigitado nem duplicado.
   */
  async function tentarDeNovo(indice: number, texto: string) {
    setMensagens((m) => m.filter((_, i) => i !== indice));
    await processarComando(texto);
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
      const resposta = await chamarComReenvio(COMANDO_PENDENCIAS);
      await atualizarSessao(resposta.session_id);
      setAcoesAgentes(resposta.actions);
      // Mesma regra do chat: se vier instrucao, o texto exibido depende do
      // resultado da execucao.
      setResumoAgentes(await executarInstrucoes(resposta));
    } catch (e) {
      setErroAgentes(registrarFalha(e));
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
    aplicarTema(nova.tema);
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
                src={
                  temaEfetivo(config.tema) === "sumi"
                    ? indicadorSumi
                    : indicadorWashi
                }
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
              onReenviar={(indice, texto) => void tentarDeNovo(indice, texto)}
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

      {splashAtivo && (
        <Splash
          onFim={() => setSplashAtivo(false)}
          tema={temaEfetivo(config.tema)}
        />
      )}
    </div>
  );
}
