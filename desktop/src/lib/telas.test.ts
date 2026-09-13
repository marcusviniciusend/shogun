/**
 * Testes das decisoes de navegacao da fiacao do App.
 *
 * O bloco F2 do roteiro de regressao (sidebar, dashboard dividido, telas)
 * conferia isso a mao: qual combinacao de view + dividido mostra o que, e
 * para onde cada acao da sidebar leva. Errar aqui nao quebra o tsc — o
 * dashboard so passa a mostrar a tela errada, em silencio.
 */
import { describe, expect, it } from "vitest";

import type { View } from "../components/Sidebar";
import type { SessaoResumoWire } from "./types";
import {
  divididoAposVer,
  ordenarSessoes,
  viewAposAlternarDividido,
  viewAposNovaConversa,
  visibilidade,
} from "./telas";

describe("visibilidade — o que o dashboard mostra", () => {
  it.each<[View, boolean, boolean, boolean, boolean]>([
    // view, dividido -> chat, agentes, conversas
    ["chat", false, true, false, false],
    ["agentes", false, false, true, false],
    ["conversas", false, false, false, true],
    ["config", false, false, false, false],
    ["chat", true, true, true, false],
    ["agentes", true, true, true, false],
    ["conversas", true, false, false, true],
    ["config", true, false, false, false],
  ])(
    "view=%s dividido=%s -> chat=%s agentes=%s conversas=%s",
    (view, dividido, chat, agentes, conversas) => {
      expect(visibilidade(view, dividido)).toEqual({ chat, agentes, conversas });
    },
  );

  it("o dividido junta chat + agentes — nunca arrasta conversas", () => {
    for (const view of ["chat", "agentes", "conversas", "config"] as View[]) {
      const telas = visibilidade(view, true);
      expect(telas.conversas && (telas.chat || telas.agentes)).toBe(false);
    }
  });

  it("config nao mostra tela nenhuma do dashboard — o App troca o main", () => {
    expect(visibilidade("config", true)).toEqual({
      chat: false,
      agentes: false,
      conversas: false,
    });
  });
});

describe("divididoAposVer — navegar desfaz o dividido, config preserva", () => {
  it.each(["chat", "agentes", "conversas"] as View[])(
    "ir para %s desliga o dividido",
    (destino) => {
      expect(divididoAposVer(destino, true)).toBe(false);
      expect(divididoAposVer(destino, false)).toBe(false);
    },
  );

  it("abrir config e um parenteses: o dividido fica como estava", () => {
    expect(divididoAposVer("config", true)).toBe(true);
    expect(divididoAposVer("config", false)).toBe(false);
  });
});

describe("viewAposAlternarDividido — dividido e sempre chat + agentes", () => {
  it.each<[View, View]>([
    // Vindo de fora do dashboard, aterra no chat.
    ["config", "chat"],
    ["conversas", "chat"],
    // Dentro do dashboard, a view fica onde esta.
    ["chat", "chat"],
    ["agentes", "agentes"],
  ])("de %s -> %s", (de, para) => {
    expect(viewAposAlternarDividido(de)).toBe(para);
  });
});

describe("viewAposNovaConversa", () => {
  it("fora do dividido, nova conversa aterra no chat", () => {
    expect(viewAposNovaConversa("agentes", false)).toBe("chat");
    expect(viewAposNovaConversa("conversas", false)).toBe("chat");
    expect(viewAposNovaConversa("chat", false)).toBe("chat");
  });

  it("no dividido, o chat ja esta visivel — a view nao muda", () => {
    expect(viewAposNovaConversa("agentes", true)).toBe("agentes");
    expect(viewAposNovaConversa("chat", true)).toBe("chat");
  });
});

describe("ordenarSessoes — mais recentemente ativa primeiro", () => {
  /** Sessao minima do fio; `atualizada_em` sem fuso, como o banco grava. */
  function sessao(id: string, atualizada_em: string): SessaoResumoWire {
    return {
      id,
      criada_em: "2026-09-01T00:00:00",
      atualizada_em,
      titulo: `Conversa ${id}`,
      total_mensagens: 1,
    };
  }

  it("ordena decrescente por atualizada_em", () => {
    const fora = [
      sessao("antiga", "2026-09-01T10:00:00"),
      sessao("recente", "2026-09-11T08:00:00"),
      sessao("media", "2026-09-05T23:59:59"),
    ];

    expect(ordenarSessoes(fora).map((s) => s.id)).toEqual([
      "recente",
      "media",
      "antiga",
    ]);
  });

  it("nao muta a lista recebida — e a resposta crua do fio", () => {
    const original = [
      sessao("a", "2026-09-01T10:00:00"),
      sessao("b", "2026-09-11T08:00:00"),
    ];
    const antes = original.map((s) => s.id);

    ordenarSessoes(original);

    expect(original.map((s) => s.id)).toEqual(antes);
  });

  it("os microssegundos do Pydantic ordenam certo na comparacao textual", () => {
    const fora = [
      sessao("primeiro", "2026-09-11T08:00:00.000001"),
      sessao("segundo", "2026-09-11T08:00:00.000002"),
    ];

    expect(ordenarSessoes(fora).map((s) => s.id)).toEqual([
      "segundo",
      "primeiro",
    ]);
  });

  it("lista vazia continua vazia, sem erro", () => {
    expect(ordenarSessoes([])).toEqual([]);
  });
});
