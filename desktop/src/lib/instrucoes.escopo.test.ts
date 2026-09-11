/**
 * O unico acoplamento do sistema que nada verificava.
 *
 * `APPS_CURADOS` (TypeScript) nomeia comandos que precisam existir, com `cmd`
 * e `args` identicos, no escopo `shell:allow-spawn` de
 * `src-tauri/capabilities/default.json` (JSON de permissao do Tauri). A
 * ligacao e por string: o `tsc` nao tem o que checar, o `cargo` nao ve o TS, e
 * um desencontro falha **so em runtime** — e ainda por cima em silencio, caindo
 * no `fallback_text`, que soa como recusa educada em vez de bug.
 *
 * Este teste fecha esse buraco nas duas direcoes: comando do mapa que nao esta
 * no capabilities, e permissao no capabilities que nao esta no mapa.
 */
import { describe, expect, it } from "vitest";

import capabilities from "../../src-tauri/capabilities/default.json";
import { APPS_CURADOS } from "./instrucoes";

/**
 * Convencao do Tauri: `"args": false` significa "nenhum argumento permitido".
 * Do lado do TS isso corresponde a lista vazia. Qualquer outro caso e
 * comparacao literal de lista.
 */
type PermissaoSpawn = { name: string; cmd: string; args: string[] | false };

function escopoDoShell(): PermissaoSpawn[] {
  const permissao = capabilities.permissions.find(
    (p): p is { identifier: string; allow: PermissaoSpawn[] } =>
      typeof p === "object" && p !== null && "identifier" in p &&
      (p as { identifier: string }).identifier === "shell:allow-spawn",
  );
  if (!permissao) {
    throw new Error(
      "capabilities/default.json nao tem mais a permissao shell:allow-spawn — " +
        "sem ela o desktop nao abre app nenhum.",
    );
  }
  return permissao.allow;
}

const ESCOPO = escopoDoShell();

describe("APPS_CURADOS x capabilities/default.json", () => {
  it("declara exatamente os mesmos comandos dos dois lados", () => {
    const noMapa = Object.values(APPS_CURADOS).map((a) => a.comando).sort();
    const noEscopo = ESCOPO.map((p) => p.name).sort();

    // Igualdade, nao inclusao: comando orfao no capabilities e permissao de
    // spawn que ninguem usa, e comando orfao no mapa e spawn recusado em
    // runtime.
    expect(noEscopo).toEqual(noMapa);
  });

  it.each(Object.entries(APPS_CURADOS))(
    'os args de "%s" batem com os do escopo',
    (_chave, alvo) => {
      const permissao = ESCOPO.find((p) => p.name === alvo.comando);
      expect(permissao, `comando "${alvo.comando}" ausente do capabilities`).toBeDefined();

      // `args: []` no mapa <-> `"args": false` no capabilities.
      const esperado = alvo.args.length === 0 ? false : alvo.args;
      expect(permissao!.args).toEqual(esperado);
    },
  );

  it("nao deixa nenhum comando do escopo sem entrada no mapa", () => {
    const comandosDoMapa = new Set(Object.values(APPS_CURADOS).map((a) => a.comando));
    const orfaos = ESCOPO.filter((p) => !comandosDoMapa.has(p.name)).map((p) => p.name);

    expect(orfaos).toEqual([]);
  });
});
