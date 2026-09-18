# L2 — Módulo `desktop/`

Cliente Tauri: front em React/TS, camada nativa em Rust. É o cliente de
referência — o mobile espelha o que se decide aqui.

## Mapa

```
src/
  App.tsx                    # raiz; troca de tela, novaConversa()
  components/
    Chat.tsx                 # conversa + botão de ditado; useEffect de limpeza cancela a gravação
    Conversas.tsx            # histórico navegável
    Configuracoes.tsx · Sidebar.tsx · Splash.tsx
    StatusServidor.tsx · PainelAgentes.tsx
  lib/
    api.ts                   # fetch via @tauri-apps/plugin-http (NÃO o fetch do navegador)
    stt.ts                   # sttDisponivel() === isTauri()
    ditado.ts                # máquina do ditado; textoUtil filtra transcrição inútil
    voz.ts                   # TTS (speechSynthesis)
    instrucoes.ts            # consumo de ClientInstruction (text × fallback_text)
    falhas.ts                # classificação de erro por tipo
    telas.ts · config.ts · types.ts
src-tauri/src/
  lib.rs · main.rs
  microfone.rs               # captura cpal; Acumulador, pico_parcial, microfone_nivel
  stt.rs                     # motor de transcrição (whisper)
```

Cada `lib/*.ts` tem `*.test.ts` ao lado — módulos puros, o plugin de shell do
Tauri é mockado. Config de teste separada em `vitest.config.ts`.

## Cuidados

- **`api.ts` usa o `fetch` do Tauri de propósito** — toda chamada ao servidor
  passa pelo Rust para não depender de origem de navegador. Isso é o motivo de o
  app não funcionar num navegador comum (ver
  [`../decisions.md`](../decisions.md), 2026-09-15).
- **O callback de áudio do `cpal` não pode alocar nem fazer I/O.** Nível vem por
  poll (`microfone_nivel`, a cada 70 ms); **ler zera a janela do pico**.
- O cronômetro conta **amostras**, não relógio de parede.
- **`instrucoes.ts`**: a regra `text` × `fallback_text` (nunca os dois) vive em
  docstring, não em tipo. Rede mecânica:
  `desktop/src/lib/instrucoes.test.ts` e `server/tests/test_comando.py`.
- `cargo test` (20 testes do microfone) **não roda no CI** — só local.
- Testes: `cd desktop && npm test`. Mexeu no desktop e no server, rode os dois.
