import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { preCarregarTema } from "./lib/config";

// Fontes embarcadas no bundle: o app funciona offline, nada vem da rede.
import "@fontsource/zen-old-mincho/400.css";
import "@fontsource/zen-old-mincho/600.css";
import "@fontsource/zen-kaku-gothic-new/300.css";
import "@fontsource/zen-kaku-gothic-new/400.css";
import "@fontsource/zen-kaku-gothic-new/500.css";

// O tema vem antes da arvore: o splash e o CSS ja nascem na cor certa, sem
// piscar do claro para o escuro em quem escolheu sumi.
const tema = await preCarregarTema();

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App temaInicial={tema} />
  </React.StrictMode>,
);
