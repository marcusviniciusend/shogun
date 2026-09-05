import { useEffect, useState } from "react";

import type { Config } from "../lib/config";

interface Props {
  config: Config;
  onSalvar: (config: Config) => void;
  onFechar: () => void;
}

export function Configuracoes({ config, onSalvar, onFechar }: Props) {
  const [serverUrl, setServerUrl] = useState(config.serverUrl);
  const [token, setToken] = useState(config.token);
  const [salvo, setSalvo] = useState(false);

  useEffect(() => {
    setServerUrl(config.serverUrl);
    setToken(config.token);
  }, [config]);

  function salvar(e: React.FormEvent) {
    e.preventDefault();
    onSalvar({ serverUrl: serverUrl.trim(), token: token.trim() });
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

        <div className="config-acoes">
          <button type="submit">Salvar</button>
          {salvo && <span className="config-salvo">Salvo ✓</span>}
        </div>
      </form>
    </section>
  );
}
