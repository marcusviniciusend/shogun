import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";

// Fontes embarcadas no bundle: o app funciona offline, nada vem da rede.
import "@fontsource/zen-old-mincho/400.css";
import "@fontsource/zen-old-mincho/600.css";
import "@fontsource/zen-kaku-gothic-new/300.css";
import "@fontsource/zen-kaku-gothic-new/400.css";
import "@fontsource/zen-kaku-gothic-new/500.css";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
