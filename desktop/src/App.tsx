import { useEffect, useRef, useState } from "react";

import indicadorSumi from "./assets/indicador-sumi.webm";
import indicadorWashi from "./assets/indicador-washi.webm";
import { Chat } from "./components/Chat";
import { Configuracoes } from "./components/Configuracoes";
import { Conversas } from "./components/Conversas";
import { PainelAgentes } from "./components/PainelAgentes";
import { Sidebar, type View } from "./components/Sidebar";
import { Splash } from "./components/Splash";
import {
  StatusServidor,
  type EstadoServidor,
} from "./components/StatusServidor";
import {
  buscarPendencias,
  carregarMensagens,
  ehErroDeConexao,
  enviarComando,
  ErroComando,
  listarSessoes,
  verificarSaude,
} from "./lib/api";
import { executarInstrucoes } from "./lib/instrucoes";
import { calar, falar, inicializarVozes } from "./lib/voz";
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
import type {
  MensagemChat,
  PendenciaWire,
  SessaoResumoWire,
} from "./lib/types";

import "./App.css";

/**
 * Cadencia do refresh automatico do painel de Agentes. So existe porque o
 * GET /pendencias e leitura direta de banco — quando o painel dependia do
 * POST /comando, cada tick custaria uma chamada de LLM.
 */
const REFRESH_AGENTES_MS = 30_000;

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

  const [pendencias, setPendencias] = useState<PendenciaWire[]>([]);
  const [totalPendencias, setTotalPendencias] = useState(0);
  const [erroAgentes, setErroAgentes] = useState<string | null>(null);
  const [agentesCarregando, setAgentesCarregando] = useState(false);
  const [agentesAtualizadoEm, setAgentesAtualizadoEm] = useState<Date | null>(
    null,
  );
  // Guarda contra sobreposicao tick automatico x clique manual — ref, e nao
  // estado, porque o intervalo le o valor da hora, nao o do render.
  const consultandoAgentesRef = useRef(false);

  const [sessoes, setSessoes] = useState<SessaoResumoWire[]>([]);
  const [sessoesErro, setSessoesErro] = useState<string | null>(null);
  const [sessoesCarregando, setSessoesCarregando] = useState(false);

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
    // A lista de vozes do WebView2 chega assincrona (voiceschanged) — armar
    // cedo para a primeira resposta ja sair na voz pt-BR quando houver.
    inicializarVozes();
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
      // A voz fala EXATAMENTE o que a bolha mostra — depois do funil de
      // instrucoes, a regra text x fallback_text vale para o audio tambem.
      // Erros (catch abaixo e pre-checagem) nao sao falados.
      if (!config.mudo) falar(textoFinal);
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

  /**
   * Recarrega o painel via GET /pendencias — leitura direta, sem LLM e sem
   * mexer na sessao de conversa. Sem pre-checagem de /health: a propria
   * chamada e igualmente barata, e uma falha de conexao ja cai no funil do
   * banner via `registrarFalha` (o que tambem pausa o refresh automatico).
   */
  async function atualizarAgentes() {
    if (consultandoAgentesRef.current) return;
    consultandoAgentesRef.current = true;
    setAgentesCarregando(true);
    setErroAgentes(null);
    try {
      const resposta = await buscarPendencias(config);
      setPendencias(resposta.pendencias);
      setTotalPendencias(resposta.total);
      setAgentesAtualizadoEm(new Date());
    } catch (e) {
      setErroAgentes(registrarFalha(e));
    } finally {
      consultandoAgentesRef.current = false;
      setAgentesCarregando(false);
    }
  }

  // Refresh automatico do painel: so com a conexao saudavel — banner ativo
  // (ou /health ainda verificando) derruba o intervalo, e ele volta sozinho
  // quando o estado retorna a "ok". O tick inicial tambem povoa o painel na
  // abertura do app, sem clique.
  useEffect(() => {
    if (estadoServidor !== "ok") return;
    void atualizarAgentes();
    const timer = setInterval(
      () => void atualizarAgentes(),
      REFRESH_AGENTES_MS,
    );
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [estadoServidor, config]);

  /** Recarrega a lista de conversas (GET /sessoes), mais recentes primeiro. */
  async function carregarSessoes() {
    setSessoesCarregando(true);
    setSessoesErro(null);
    try {
      const resposta = await listarSessoes(config);
      setSessoes(
        [...resposta.sessoes].sort((a, b) =>
          b.atualizada_em.localeCompare(a.atualizada_em),
        ),
      );
    } catch (e) {
      setSessoesErro(registrarFalha(e));
    } finally {
      setSessoesCarregando(false);
    }
  }

  // Entrar na tela de conversas ja carrega a lista — o botao Atualizar fica
  // para quem deixou a tela aberta.
  useEffect(() => {
    if (view === "conversas") void carregarSessoes();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view]);

  /**
   * Abre uma conversa antiga: carrega o historico, troca a sessao ativa (e a
   * persistida) e volta para o chat — a proxima mensagem continua AQUELA
   * conversa.
   */
  async function abrirConversa(id: string) {
    // Trocar de conversa cala a fala da anterior — o audio pertence ao
    // contexto que estava na tela.
    calar();
    setSessoesCarregando(true);
    setSessoesErro(null);
    try {
      const resposta = await carregarMensagens(config, id);
      setMensagens(
        resposta.mensagens.map((m) => ({ autor: m.autor, texto: m.texto })),
      );
      setSessionId(resposta.session_id);
      await salvarSessionId(resposta.session_id);
      setView("chat");
    } catch (e) {
      setSessoesErro(registrarFalha(e));
    } finally {
      setSessoesCarregando(false);
    }
  }

  async function novaConversa() {
    calar();
    setMensagens([]);
    setSessionId(null);
    await salvarSessionId(null);
  }

  /**
   * Liga/desliga o mudo e persiste na hora — e um interruptor, nao um
   * formulario. Mutar tambem cala a fala em curso.
   */
  async function alternarMudo() {
    const nova = { ...config, mudo: !config.mudo };
    if (nova.mudo) calar();
    setConfig(nova);
    await salvarConfig(nova);
  }

  async function salvar(nova: Config) {
    if (nova.mudo) calar();
    setConfig(nova);
    aplicarTema(nova.tema);
    await salvarConfig(nova);
    // URL ou token novos: o estado anterior nao diz mais nada sobre este alvo.
    await checarSaude(nova);
  }

  // O dividido so junta chat + agentes; conversas e uma tela propria.
  const emDashboard = view === "chat" || view === "agentes";
  const mostraChat = view === "chat" || (dividido && emDashboard);
  const mostraAgentes = view === "agentes" || (dividido && emDashboard);
  const mostraConversas = view === "conversas";

  return (
    <div className="app">
      <Sidebar
        view={view}
        dividido={dividido}
        mudo={config.mudo}
        onAlternarMudo={() => void alternarMudo()}
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
          // Dividido e sempre chat + agentes: vindo de outra tela, aterra no chat.
          if (view === "config" || view === "conversas") setView("chat");
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
          {mostraConversas && (
            <Conversas
              sessoes={sessoes}
              sessionIdAtual={sessionId}
              erro={sessoesErro}
              carregando={sessoesCarregando}
              onAtualizar={() => void carregarSessoes()}
              onAbrir={(id) => void abrirConversa(id)}
            />
          )}
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
              pendencias={pendencias}
              total={totalPendencias}
              erro={erroAgentes}
              carregando={agentesCarregando}
              atualizadoEm={agentesAtualizadoEm}
              onAtualizar={() => void atualizarAgentes()}
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
