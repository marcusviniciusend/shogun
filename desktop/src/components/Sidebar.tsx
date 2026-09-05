export type View = "chat" | "agentes" | "config";

interface Props {
  view: View;
  dividido: boolean;
  onNovaConversa: () => void;
  onVer: (view: View) => void;
  onAlternarDividido: () => void;
}

/**
 * Barra lateral de navegacao: fina (so icones), expande no hover mostrando
 * os rotulos.
 *
 * O modo dividido (chat + agentes lado a lado) e um TOGGLE com icone
 * proprio, em vez de opcao enterrada nas configuracoes: fica visivel o
 * tempo todo, custa um clique e o estado ativo e legivel no proprio icone.
 * Clicar em Conversa ou Agentes com o dividido ativo volta para a view
 * unica daquele item — o caminho de volta e o mesmo da ida.
 */
export function Sidebar({
  view,
  dividido,
  onNovaConversa,
  onVer,
  onAlternarDividido,
}: Props) {
  const ativa = (v: View) =>
    view === v || (dividido && view !== "config" && v !== "config");

  return (
    <nav className="sidebar" aria-label="Navegação">
      <button
        type="button"
        className="sidebar-item"
        onClick={onNovaConversa}
        title="Nova conversa"
      >
        <svg viewBox="0 0 20 20" aria-hidden>
          <path d="M10 4.5v11M4.5 10h11" />
        </svg>
        <span>Nova conversa</span>
      </button>

      <div className="sidebar-divisor" />

      <button
        type="button"
        className={`sidebar-item${ativa("chat") ? " ativa" : ""}`}
        onClick={() => onVer("chat")}
        title="Conversa"
      >
        <svg viewBox="0 0 20 20" aria-hidden>
          <path d="M3.5 5.5h13v8h-7l-3.5 3v-3h-2.5z" />
        </svg>
        <span>Conversa</span>
      </button>

      <button
        type="button"
        className={`sidebar-item${ativa("agentes") ? " ativa" : ""}`}
        onClick={() => onVer("agentes")}
        title="Agentes"
      >
        <svg viewBox="0 0 20 20" aria-hidden>
          <circle cx="7" cy="7.5" r="2.5" />
          <circle cx="13.5" cy="9" r="2" />
          <path d="M3.5 16c0-2.2 1.6-3.5 3.5-3.5s3.5 1.3 3.5 3.5M11.8 16c.2-1.7 1.2-2.8 2.7-2.8 1.1 0 2 .6 2.5 1.6" />
        </svg>
        <span>Agentes</span>
      </button>

      <button
        type="button"
        className={`sidebar-item${dividido ? " ativa" : ""}`}
        onClick={onAlternarDividido}
        title={dividido ? "Sair da visualização dividida" : "Visualização dividida"}
        aria-pressed={dividido}
      >
        <svg viewBox="0 0 20 20" aria-hidden>
          <rect x="3.5" y="4.5" width="13" height="11" rx="1" />
          <path d="M12 4.5v11" />
        </svg>
        <span>Dividido</span>
      </button>

      <div className="sidebar-vao" />

      <button
        type="button"
        className={`sidebar-item${view === "config" ? " ativa" : ""}`}
        onClick={() => onVer("config")}
        title="Configurações"
      >
        <svg viewBox="0 0 20 20" aria-hidden>
          <path d="M4 6.5h12M4 10h12M4 13.5h12" />
          <circle cx="8" cy="6.5" r="1.4" fill="var(--papel)" />
          <circle cx="12.5" cy="10" r="1.4" fill="var(--papel)" />
          <circle cx="6.5" cy="13.5" r="1.4" fill="var(--papel)" />
        </svg>
        <span>Configurações</span>
      </button>
    </nav>
  );
}
