/**
 * Testes da traducao de falha do cliente HTTP.
 *
 * O que se verifica aqui e o `tipo` de `ErroComando` e a frase que chega ao
 * usuario — os dois pedacos que o roteiro de regressao manual exercita a mao
 * nos blocos F1 (indicador de conexao), F3 (erro por tipo) e F4 (429). O tipo
 * e o que decide a reacao da UI (banner do topo x bolha no chat, reenviar x
 * nao reenviar); errar o tipo nao quebra o `tsc` e nao aparece em log nenhum,
 * so em runtime, na cara de quem usa.
 *
 * O `fetch` mockado e o do tauri-plugin-http, nao o do webview: o modulo de
 * producao importa aquele e so aquele. As respostas sao `Response` de verdade
 * (Node 18+), para que `ok`, `status`, `headers.get` e `json()` se comportem
 * como no app em vez de como um dube complacente.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Config } from "./config";
import {
  ErroComando,
  buscarPendencias,
  carregarMensagens,
  ehErroDeConexao,
  enviarComando,
  listarSessoes,
  verificarSaude,
} from "./api";

const { fetchMock } = vi.hoisted(() => ({ fetchMock: vi.fn() }));

vi.mock("@tauri-apps/plugin-http", () => ({ fetch: fetchMock }));

const CONFIG: Config = {
  serverUrl: "http://localhost:8000",
  token: "",
  tema: "washi",
  mudo: false,
};

const comToken = (token: string): Config => ({ ...CONFIG, token });

/** Corpo JSON valido de POST /comando, para os casos de caminho feliz. */
const CORPO_OK = { session_id: "s1", text: "Bom dia, Marcus.", actions: [] };

function json(corpo: unknown, status = 200, headers?: HeadersInit): Response {
  return new Response(JSON.stringify(corpo), {
    status,
    headers: { "content-type": "application/json", ...(headers ?? {}) },
  });
}

/**
 * `fetch` que nunca responde e so falha quando o AbortController do modulo
 * dispara — e assim que um servidor travado se comporta.
 */
function fetchPendurado() {
  return (_url: string, init: { signal: AbortSignal }) =>
    new Promise((_ok, falhar) => {
      init.signal.addEventListener("abort", () =>
        falhar(new Error("Request canceled")),
      );
    });
}

/** Captura o `ErroComando` de uma promessa que precisa falhar. */
async function capturar(promessa: Promise<unknown>): Promise<ErroComando> {
  try {
    await promessa;
  } catch (e) {
    expect(e).toBeInstanceOf(ErroComando);
    return e as ErroComando;
  }
  throw new Error("a chamada resolveu quando devia ter falhado");
}

beforeEach(() => {
  vi.clearAllMocks();
  // Toda falha registra a causa crua no console de proposito (foi a falta
  // disso que obrigou a diagnosticar com netstat no incidente de 05/09).
  // Silenciar mantem a saida do teste legivel sem mudar o comportamento.
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  vi.useRealTimers();
});

describe("traducao de falha de rede (F1.2, F1.5, F3.1)", () => {
  it.each([
    [
      "conexao recusada (os error 10061 no Windows)",
      "error trying to connect: tcp connect error (os error 10061)",
      "Nao ha servidor escutando em http://localhost:8000.",
    ],
    [
      "ECONNREFUSED",
      "request error: ECONNREFUSED",
      "Nao ha servidor escutando em http://localhost:8000.",
    ],
    [
      "conexao aceita e sem resposta",
      "operation timed out",
      "http://localhost:8000 aceitou a conexao mas nao respondeu a tempo.",
    ],
    [
      "host que nao resolve",
      "dns error: failed to lookup address information",
      "Nao consegui resolver o endereco de http://localhost:8000.",
    ],
    [
      "nome de host desconhecido",
      "nodename nor servname provided",
      "Nao consegui resolver o endereco de http://localhost:8000.",
    ],
  ])("%s vira uma frase com a causa nomeada", async (_caso, cru, trecho) => {
    fetchMock.mockRejectedValueOnce(new Error(cru));

    const erro = await capturar(verificarSaude(CONFIG));

    expect(erro.tipo).toBe("rede");
    expect(erro.message).toContain(trecho);
  });

  it("falha desconhecida carrega o texto original em vez de engolir a causa", async () => {
    // O plugin devolve a mensagem do reqwest, que nao e contrato estavel: o
    // caso nao reconhecido PRECISA mostrar o texto cru, senao volta o problema
    // que este arquivo de producao nasceu para resolver.
    fetchMock.mockRejectedValueOnce(new Error("invalid peer certificate"));

    const erro = await capturar(verificarSaude(CONFIG));

    expect(erro.tipo).toBe("rede");
    expect(erro.message).toContain(
      "Falha de rede ao falar com http://localhost:8000",
    );
    expect(erro.message).toContain("invalid peer certificate");
  });

  it("guarda a excecao crua em causa, fora da mensagem exibida", async () => {
    const cru = new Error("error trying to connect: tcp connect error");
    fetchMock.mockRejectedValueOnce(cru);

    const erro = await capturar(verificarSaude(CONFIG));

    expect(erro.causa).toBe(cru);
  });
});

describe("verificarSaude — GET /health (F1.1, F1.4, F3.7)", () => {
  it("servidor de pe resolve sem erro e nao manda token", async () => {
    fetchMock.mockResolvedValueOnce(json({ status: "ok" }));

    await expect(verificarSaude(comToken("segredo"))).resolves.toBeUndefined();

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://localhost:8000/health");
    expect(init.method).toBe("GET");
    // /health e barato de proposito: sem token e sem passar pelo LLM.
    expect(init.headers).toBeUndefined();
  });

  it("outro programa na porta (HTTP 404) vira erro http, nao rede", async () => {
    fetchMock.mockResolvedValueOnce(json({ detail: "nao existe" }, 404));

    const erro = await capturar(verificarSaude(CONFIG));

    expect(erro.tipo).toBe("http");
    expect(erro.message).toContain("respondeu HTTP 404 em /health");
    expect(erro.message).toContain("outro programa ocupando essa porta");
  });

  it("servidor que aceita e nunca responde vira timeout em 4s, sem pendurar", async () => {
    vi.useFakeTimers();
    fetchMock.mockImplementationOnce(fetchPendurado());

    const promessa = capturar(verificarSaude(CONFIG));
    await vi.advanceTimersByTimeAsync(4000);
    const erro = await promessa;

    // O limite proprio do /health e o que impede o indicador de ficar preso
    // em "verificando" para sempre.
    expect(erro.tipo).toBe("timeout");
  });
});

describe("ehErroDeConexao — o que vai para o banner do topo (F3.1, F3.8)", () => {
  it.each([
    ["rede", true],
    ["timeout", true],
    ["auth", false],
    ["llm_indisponivel", false],
    ["rate_limit", false],
    ["http", false],
    ["formato", false],
  ] as const)("%s -> %s", (tipo, esperado) => {
    expect(ehErroDeConexao(new ErroComando("x", tipo))).toBe(esperado);
  });

  it("erro que nao e ErroComando nunca conta como falha de conexao", () => {
    expect(ehErroDeConexao(new Error("qualquer coisa"))).toBe(false);
    expect(ehErroDeConexao("string solta")).toBe(false);
    expect(ehErroDeConexao(null)).toBe(false);
  });
});

describe("enviarComando — requisicao (F2.1, F5.1)", () => {
  it("monta o corpo do contrato e manda o Bearer quando ha token", async () => {
    fetchMock.mockResolvedValueOnce(json(CORPO_OK));

    await enviarComando(comToken("segredo"), "bom dia", "s1");

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://localhost:8000/comando");
    expect(init.method).toBe("POST");
    expect(init.headers.Authorization).toBe("Bearer segredo");
    expect(JSON.parse(init.body)).toEqual({
      session_id: "s1",
      text: "bom dia",
      client: "desktop",
    });
  });

  it("sem token configurado, nenhum header Authorization e enviado", async () => {
    fetchMock.mockResolvedValueOnce(json(CORPO_OK));

    await enviarComando(CONFIG, "bom dia", null);

    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers.Authorization).toBeUndefined();
    // Conversa nova sai com session_id nulo — e o servidor que abre a sessao.
    expect(JSON.parse(init.body).session_id).toBeNull();
  });

  it("resposta valida volta como o corpo do contrato", async () => {
    fetchMock.mockResolvedValueOnce(json(CORPO_OK));

    await expect(enviarComando(CONFIG, "bom dia", null)).resolves.toEqual(
      CORPO_OK,
    );
  });
});

describe("enviarComando — erro por status (F3.3, F3.4, F3.5)", () => {
  it.each([401, 403])(
    "HTTP %s com token configurado vira auth apontando o token",
    async (status) => {
      fetchMock.mockResolvedValueOnce(
        json({ detail: "nao autorizado" }, status),
      );

      const erro = await capturar(enviarComando(comToken("errado"), "oi", null));

      expect(erro.tipo).toBe("auth");
      expect(erro.message).toContain(`recusou o token (HTTP ${status})`);
    },
  );

  it("401 sem token configurado pede para preencher o token", async () => {
    fetchMock.mockResolvedValueOnce(json({ detail: "nao autorizado" }, 401));

    const erro = await capturar(enviarComando(CONFIG, "oi", null));

    expect(erro.tipo).toBe("auth");
    expect(erro.message).toContain("nenhum token esta configurado");
    expect(erro.message).toContain("SHOGUN_AUTH_TOKEN");
  });

  it("503 vira llm_indisponivel — o unico tipo com reenvio automatico", async () => {
    fetchMock.mockResolvedValueOnce(json({ detail: "modelo frio" }, 503));

    const erro = await capturar(enviarComando(CONFIG, "oi", null));

    expect(erro.tipo).toBe("llm_indisponivel");
    expect(erro.message).toContain("(503)");
  });

  it("status inesperado vira http generico, sem reenvio", async () => {
    fetchMock.mockResolvedValueOnce(json({ detail: "boom" }, 500));

    const erro = await capturar(enviarComando(CONFIG, "oi", null));

    expect(erro.tipo).toBe("http");
    expect(erro.message).toContain("HTTP 500");
  });

  it("200 com corpo que nao e JSON vira formato", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response("nao sou json", { status: 200 }),
    );

    const erro = await capturar(enviarComando(CONFIG, "oi", null));

    expect(erro.tipo).toBe("formato");
    expect(erro.message).toContain("fora do formato esperado");
  });

  it("estouro do limite vira timeout, com frase distinta de servidor fora do ar", async () => {
    vi.useFakeTimers();
    fetchMock.mockImplementationOnce(fetchPendurado());

    const promessa = capturar(enviarComando(CONFIG, "oi", null));
    await vi.advanceTimersByTimeAsync(60_000);
    const erro = await promessa;

    expect(erro.tipo).toBe("timeout");
    // "recebeu o comando mas nao respondeu": o servidor esta la, travado — a
    // mensagem de rede diria o contrario.
    expect(erro.message).toContain("recebeu o comando");
    expect(erro.message).toContain("60 segundos");
  });
});

describe("429 e o Retry-After (F4.1)", () => {
  it.each([
    ["30", 30, "aguarde 30 segundos"],
    ["1", 1, "aguarde 1 segundo e"],
    ["0", 0, "aguarde 0 segundos"],
    // Fracao arredonda para cima: esperar de menos volta a tomar 429.
    ["2.4", 3, "aguarde 3 segundos"],
  ])(
    "Retry-After %s vira %s segundos na mensagem e no campo",
    async (header, segundos, trecho) => {
      fetchMock.mockResolvedValueOnce(
        json({ detail: "devagar" }, 429, { "retry-after": header as string }),
      );

      const erro = await capturar(enviarComando(CONFIG, "oi", null));

      expect(erro.tipo).toBe("rate_limit");
      expect(erro.retryAfterSegundos).toBe(segundos);
      expect(erro.message).toContain(trecho);
    },
  );

  it("Retry-After em HTTP-date vira a espera restante em segundos", async () => {
    const alvo = Date.parse("Wed, 21 Oct 2015 07:28:00 GMT");
    vi.useFakeTimers();
    vi.setSystemTime(alvo - 90_000);
    fetchMock.mockResolvedValueOnce(
      json({ detail: "devagar" }, 429, {
        "retry-after": "Wed, 21 Oct 2015 07:28:00 GMT",
      }),
    );

    const erro = await capturar(enviarComando(CONFIG, "oi", null));

    expect(erro.retryAfterSegundos).toBe(90);
  });

  it("HTTP-date ja vencida nao vira espera negativa", async () => {
    const alvo = Date.parse("Wed, 21 Oct 2015 07:28:00 GMT");
    vi.useFakeTimers();
    vi.setSystemTime(alvo + 120_000);
    fetchMock.mockResolvedValueOnce(
      json({ detail: "devagar" }, 429, {
        "retry-after": "Wed, 21 Oct 2015 07:28:00 GMT",
      }),
    );

    const erro = await capturar(enviarComando(CONFIG, "oi", null));

    expect(erro.retryAfterSegundos).toBe(0);
  });

  it.each([
    ["ausente", undefined],
    ["ilegivel", "logo mais"],
  ])("Retry-After %s cai na frase generica, sem numero", async (_caso, header) => {
    fetchMock.mockResolvedValueOnce(
      json({ detail: "devagar" }, 429, header ? { "retry-after": header } : {}),
    );

    const erro = await capturar(enviarComando(CONFIG, "oi", null));

    expect(erro.tipo).toBe("rate_limit");
    expect(erro.retryAfterSegundos).toBeUndefined();
    expect(erro.message).toContain("aguarde um instante");
  });

  it("Retry-After negativo nunca vira espera negativa", async () => {
    // Header malformado: qualquer que seja a leitura, a UI nao pode receber um
    // numero negativo para contar.
    fetchMock.mockResolvedValueOnce(
      json({ detail: "devagar" }, 429, { "retry-after": "-5" }),
    );

    const erro = await capturar(enviarComando(CONFIG, "oi", null));

    expect(erro.tipo).toBe("rate_limit");
    expect(
      erro.retryAfterSegundos === undefined || erro.retryAfterSegundos >= 0,
    ).toBe(true);
  });
});

describe("rotas de leitura — getAutenticado (F3.6, F4.1)", () => {
  it("listarSessoes chama /sessoes com o Bearer", async () => {
    fetchMock.mockResolvedValueOnce(json({ sessoes: [] }));

    await expect(listarSessoes(comToken("segredo"))).resolves.toEqual({
      sessoes: [],
    });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://localhost:8000/sessoes");
    expect(init.method).toBe("GET");
    expect(init.headers.Authorization).toBe("Bearer segredo");
  });

  it("carregarMensagens escapa o id na URL", async () => {
    fetchMock.mockResolvedValueOnce(json({ mensagens: [] }));

    await carregarMensagens(CONFIG, "id com espaco/barra");

    expect(fetchMock.mock.calls[0][0]).toBe(
      "http://localhost:8000/sessoes/id%20com%20espaco%2Fbarra/mensagens",
    );
  });

  it("404 diz qual rota falta e manda atualizar o servidor", async () => {
    // Servidor de versao anterior ao contrato desta tela: a tela nao pode
    // quebrar, precisa explicar.
    fetchMock.mockResolvedValueOnce(json({ detail: "rota inexistente" }, 404));

    const erro = await capturar(listarSessoes(CONFIG));

    expect(erro.tipo).toBe("http");
    expect(erro.message).toContain("nao conhece /sessoes");
    expect(erro.message).toContain("as conversas");
  });

  it("404 nomeia o recurso de cada rota, nao um texto generico", async () => {
    fetchMock.mockResolvedValueOnce(json({ detail: "rota inexistente" }, 404));

    const erro = await capturar(buscarPendencias(CONFIG));

    expect(erro.message).toContain("nao conhece /pendencias");
    expect(erro.message).toContain("as pendencias");
  });

  it.each([401, 403])("HTTP %s na leitura vira auth", async (status) => {
    fetchMock.mockResolvedValueOnce(json({ detail: "nao" }, status));

    const erro = await capturar(buscarPendencias(comToken("errado")));

    expect(erro.tipo).toBe("auth");
    expect(erro.message).toContain(`recusou o token (HTTP ${status})`);
  });

  it("429 na leitura usa o mesmo funil de rate limit do /comando", async () => {
    fetchMock.mockResolvedValueOnce(
      json({ detail: "devagar" }, 429, { "retry-after": "12" }),
    );

    const erro = await capturar(buscarPendencias(CONFIG));

    expect(erro.tipo).toBe("rate_limit");
    expect(erro.retryAfterSegundos).toBe(12);
  });

  it("status inesperado nomeia o recurso que falhou", async () => {
    fetchMock.mockResolvedValueOnce(json({ detail: "boom" }, 500));

    const erro = await capturar(buscarPendencias(CONFIG));

    expect(erro.tipo).toBe("http");
    expect(erro.message).toContain("HTTP 500 ao carregar as pendencias");
  });

  it("corpo fora do formato na leitura vira formato", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response("<html>proxy</html>", { status: 200 }),
    );

    const erro = await capturar(listarSessoes(CONFIG));

    expect(erro.tipo).toBe("formato");
    expect(erro.message).toContain("as conversas fora do formato esperado");
  });

  it("queda de rede na leitura entra no mesmo funil de conexao do chat", async () => {
    // Achado 6 do levantamento: a mesma queda nao pode parecer dois problemas.
    fetchMock.mockRejectedValueOnce(new Error("error trying to connect"));

    const erro = await capturar(buscarPendencias(CONFIG));

    expect(ehErroDeConexao(erro)).toBe(true);
    expect(erro.message).toContain("Nao ha servidor escutando em");
  });

  it("leitura pendurada estoura em 8s, nao nos 60s do /comando", async () => {
    vi.useFakeTimers();
    fetchMock.mockImplementationOnce(fetchPendurado());

    const promessa = capturar(listarSessoes(CONFIG));
    await vi.advanceTimersByTimeAsync(8000);
    const erro = await promessa;

    expect(erro.tipo).toBe("timeout");
    expect(erro.message).toContain("8 segundos");
  });
});
