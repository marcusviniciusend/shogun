import { useEffect, useState } from "react";

import { aplicarTema, type Config, type Tema } from "../lib/config";

const TEMAS: Array<{ valor: Tema; rotulo: string }> = [
  { valor: "washi", rotulo: "Washi" },
  { valor: "sumi", rotulo: "Sumi" },
  { valor: "sistema", rotulo: "Sistema" },
];

interface Props {
  config: Config;
  onSalvar: (config: Config) => void;
  onFechar: () => void;
}

export function Configuracoes({ config, onSalvar, onFechar }: Props) {
  const [serverUrl, setServerUrl] = useState(config.serverUrl);
  const [token, setToken] = useState(config.token);
  const [tema, setTema] = useState<Tema>(config.tema);
  const [salvo, setSalvo] = useState(false);

  useEffect(() => {
    setServerUrl(config.serverUrl);
    setToken(config.token);
    setTema(config.tema);
  }, [config]);

  /**
   * Aparencia muda na hora de clicar, sem esperar o Salvar: escolher tema e
   * uma decisao visual, e olhar o resultado E a decisao. O valor so persiste
   * no Salvar; sair sem salvar volta ao que estava.
   */
  function escolherTema(novo: Tema) {
    setTema(novo);
    aplicarTema(novo);
  }

  function salvar(e: React.FormEvent) {
    e.preventDefault();
    onSalvar({ serverUrl: serverUrl.trim(), token: token.trim(), tema });
    setSalvo(true);
    setTimeout(() => setSalvo(false), 2000);
  }

  return (
    <section className="painel configuracoes">
      <header className="painel-cabecalho">
        <h2>Configurações</h2>
        <button type="button" className="botao-secundario" onClick={onFechar}>
          Voltar
        </button>
      </header>

      <form onSubmit={salvar} className="config-form">
        <label>
          URL do servidor
          <input
            type="url"
            value={serverUrl}
            onChange={(e) => setServerUrl(e.target.value)}
            placeholder="http://localhost:8000"
            required
          />
          <small>
            Local: http://localhost:8000. Remoto: o IP Tailscale do servidor,
            ex. http://100.x.y.z:8000.
          </small>
        </label>

        <label>
          Token de autenticação (Bearer)
          <input
            type="password"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder="SHOGUN_AUTH_TOKEN do servidor"
            autoComplete="off"
          />
          <small>
            Opcional quando o servidor roda local (127.0.0.1) sem token;
            obrigatório quando ele escuta na rede.
          </small>
        </label>

        <fieldset className="config-tema">
          <legend>Aparência</legend>
          <div className="config-tema-opcoes" role="radiogroup" aria-label="Tema">
            {TEMAS.map((t) => (
              <button
                key={t.valor}
                type="button"
                role="radio"
                aria-checked={tema === t.valor}
                className={`tema-opcao${tema === t.valor ? " ativa" : ""}`}
                onClick={() => escolherTema(t.valor)}
              >
                {t.rotulo}
              </button>
            ))}
          </div>
        </fieldset>

        <div className="config-acoes">
          <button type="submit">Salvar</button>
          {salvo && <span className="config-salvo">Salvo ✓</span>}
        </div>
      </form>
    </section>
  );
}
