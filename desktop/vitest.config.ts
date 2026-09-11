import { defineConfig } from "vitest/config";

/**
 * Config separada da `vite.config.ts` de proposito: os testes sao de modulo
 * puro (nao montam componente React), entao nao precisam do plugin de JSX nem
 * das opcoes de dev server do Tauri — e a config do app fica intocada.
 */
export default defineConfig({
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
