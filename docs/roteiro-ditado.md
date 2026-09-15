# Roteiro de regressão manual — ditado por voz (STT)

Roteiro de conferência do ditado por clique do cliente desktop, introduzido
na v1.1 pelos PRs #61–#63 (motor whisper.cpp, captura) e #65 (captura nativa
com cpal e a fiação ponta a ponta).

Existe pelo mesmo motivo do [`roteiro-regressao-v1.md`](roteiro-regressao-v1.md):
a suíte automatizada cobre a lógica pura dos dois lados — `cargo test` cobre a
aritmética de áudio em Rust (mescla de canais, reamostragem, acumulador) e o
vitest cobre a máquina de estados do ditado e o wrapper de `invoke` — mas
**nenhuma das duas toca em microfone, dispositivo de áudio ou modelo de 465 MB
no disco**. Tudo abaixo só se verifica com o app na tela e voz de verdade.

**Este bloco é 100% humano.** Nenhum agente do projeto tem microfone; nenhum
passo daqui pode ser delegado.

A numeração continua a do roteiro da v1.0, que termina em `F9 — Painel de
Agentes`. Os itens são numerados (`F10.4`) para poder reportar "F10.4 falhou"
sem transcrever o passo.

---

## 0. Preparo

1. **Chave de privacidade do Windows LIGADA**: Configurações → Privacidade e
   segurança → Microfone → *"Permitir que aplicativos da área de trabalho
   acessem seu microfone"*.

   > ⚠️ **Não existe mais prompt de permissão.** A captura é WASAPI direto via
   > `cpal`, não passa pelo WebView2. Com a chave desligada o sistema **recusa**
   > — vira erro tratado (F10.11), não pergunta na tela. Quem esperar o prompt
   > que a versão `getUserMedia` mostrava vai concluir errado que travou.

2. **Ambiente de build preparado.** O ditado depende do motor compilado:
   `python scripts/checar_ambiente_desktop.py` tem que sair sem itens faltando.
   Se faltar, `--exports` imprime as linhas prontas. Detalhes e sintomas em
   `desktop/README.md`, seção "Pré-requisitos de build nativo".

3. **Rodar o build Tauri** (`npm run tauri dev`) **com o terminal do processo
   visível** — o F10.5 lê o log do lado Rust, que **não** aparece no console do
   WebView2.

4. Servidor de pé, como no roteiro da v1.0 (`SHOGUN_LLM_PROVIDER=deterministico`
   basta para os passos que mandam comando).

5. **Custos de primeira execução, esperados e não repetidos:** o modelo baixa
   ~465 MB (F10.1/F10.2) e a primeira transcrição carrega o modelo na memória —
   alguns segundos, uma vez por sessão do app.

---

## F10 — Ditado (clique alterna, captura nativa)

### Modelo — primeira execução

| # | Passo | Resultado esperado | Onde olhar quando falhar |
|---|---|---|---|
| F10.0 | Abrir o app (build Tauri) | Botão de **microfone** aparece ao lado de "Enviar" | `sttDisponivel()`/`isTauri()` em `lib/stt.ts`; `DITADO_DISPONIVEL` em `App.tsx` |
| F10.1 | Abrir com o modelo ainda não baixado | Sob a entrada: "A voz precisa do modelo…" + botão **Baixar (465 MB)** — **sem ter falado nada antes** | `statusModeloStt()` no `useEffect` de montagem do `Chat.tsx` |
| F10.2 | Clicar em **Baixar** | Barra de progresso avançando, "N MB de 465 MB (X%)"; ao terminar a oferta some | evento `stt-download-progresso`; `baixarModeloStt` |
| F10.3 | Cortar a rede no meio do download | Mensagem de "interrompido no meio"; a oferta **continua de pé**; clicar de novo rebaixa do zero e conclui | `stt_baixar_modelo` — o arquivo `.baixando` é descartado, o SHA-256 é revalidado |

### Ciclo básico

| # | Passo | Resultado esperado | Onde olhar quando falhar |
|---|---|---|---|
| F10.4 | Clicar no **microfone**, falar "abre a calculadora", clicar de novo | Entre os cliques: ícone em bengara pulsando + "Ouvindo — clique para enviar."; ao segundo clique, "Transcrevendo…"; depois o texto **entra como mensagem do usuário** e o comando executa | `criarControleDitado` em `lib/ditado.ts`; `microfone_parar_e_transcrever` |
| F10.5 | Conferir o **terminal do `tauri dev`** (não o console do WebView2) | Linha `[shogun] microfone: N amostras a 48000 Hz -> M a 16000 Hz (~2.1s), pico 0.34` — **pico > 0** | `eprintln` em `microfone_parar_e_transcrever`. **Pico 0 = microfone mudo no sistema**, não bug do app |
| F10.6 | Repetir o F10.4 **com a voz ligada**, falando por cima da resposta anterior | O Shogun **cala** antes de o microfone abrir; nada de eco do TTS dentro da transcrição | `calar()` antes de `iniciarGravacao` em `criarControleDitado` |
| F10.19 | Clicar no **microfone** e, sem falar, clicar de novo **imediatamente** (< 300 ms) | A captura é descartada: nada enviado, nenhum erro, e o microfone **não fica aberto** (o ícone do Windows some) | fase `abrindo` + `cancelarGravacao` no caminho `desistiuAoAbrir` |

### Entrada e interrupção

| # | Passo | Resultado esperado | Onde olhar quando falhar |
|---|---|---|---|
| F10.7 | Gravando, **clicar fora do botão** (no chat, na barra lateral) e só então clicar no microfone | A gravação **sobrevive** ao clique fora — ela só termina no clique do próprio botão | `alternarFalar` em `Chat.tsx`: não há mais captura de ponteiro para perder |
| F10.8 | Gravando, **arrastar a janela** pela barra de título e falar enquanto arrasta | Continua gravando; ao clicar no microfone, transcreve normalmente | idem — o gesto do ponteiro deixou de participar do ciclo |
| F10.9 | Focar o microfone pelo teclado (Tab) e apertar **espaço**, depois **espaço** de novo | Mesmo ciclo do mouse; segurar o espaço apertado **não** dispara nada repetido | `onClick` nativo do `<button>` — sem handler de tecla próprio |
| F10.10 | Gravando, clicar em "Nova conversa" ou trocar de tela | Gravação abortada, **microfone fecha** (ícone do Windows some), nada é enviado | `useEffect` de desmontagem → `controle.cancelar()` → `microfone_cancelar` |
| F10.18 | Falar e, **durante o "Transcrevendo…"**, tentar clicar no microfone de novo | Botão desabilitado; nada de duas transcrições disputando o chat | `disabled` em `estadoDitado === "transcrevendo"` |

### Falhas de ambiente

| # | Passo | Resultado esperado | Onde olhar quando falhar |
|---|---|---|---|
| F10.11 | **Desligar** a chave de privacidade do Windows e clicar no **microfone** | Mensagem apontando Configurações → Privacidade e segurança → Microfone; o estado nem sai do ocioso; **nenhum prompt aparece** | `traduzir_erro_cpal` / `cpal::ErrorKind::PermissionDenied` |
| F10.12 | Abrir outro app segurando o microfone em modo exclusivo e tentar gravar | "O microfone está em uso por outro aplicativo." | `ErrorKind::DeviceBusy` |
| F10.13 | Desconectar o microfone USB e tentar gravar | "Nenhum microfone disponível." | `default_input_device()` devolvendo `None` |
| F10.16 | Com o servidor fora do ar (banner do topo ativo) | Botão de **microfone** **desabilitado** — as mesmas condições que travam o campo de texto | `podeGravar` em `lib/ditado.ts` |
| F10.17 | Renomear/apagar o `ggml-small.bin` em `%APPDATA%\...\modelos-stt` **com o app aberto** e tentar falar | O erro vira **oferta de download** de novo, não uma frase de erro repetida | `modeloAusente` em `FalhaDitado`; `aoErro` no `Chat.tsx` |

### Casos limite

| # | Passo | Resultado esperado | Onde olhar quando falhar |
|---|---|---|---|
| F10.14 | Falar algo curto ("sim") | Transcreve mesmo abaixo de 1 s — o Rust completa com silêncio até 1,1 s (o whisper.cpp recusa áudio menor) | `MINIMO_AMOSTRAS` em `stt.rs` |
| F10.15 | Gravar **em silêncio** por ~3 s e clicar para encerrar | Volta ao ocioso sem enviar nada e **sem erro** — transcrição vazia não vira comando | `textoUtil` em `lib/ditado.ts` |

---

## O que este roteiro NÃO cobre

Registrado pelo autor da implementação, para não parecer esquecimento:

- **Qualidade real da transcrição em português.** Nenhum teste julga isso — só
  o ouvido. É aqui que entra a régua do
  [`stt-desktop-design.md`](stt-desktop-design.md): se a espera incomodar,
  **o plano B documentado é trocar o modelo `small` por `base`**, não mexer em
  arquitetura. Vale anotar o tempo percebido entre soltar o botão e o texto
  aparecer.
- **Microfone com taxa de amostragem exótica.** O `reamostrar` tem teste para
  44,1 kHz e 48 kHz; um dispositivo a 96 kHz cai na razão inteira 6 e **nunca
  foi exercitado com som de verdade**.
- **Formatos de amostra `DsdU8`, `I24` e `U24`.** O código os **recusa com erro
  tipado** em vez de tentar interpretar — o comportamento é deliberado, mas não
  foi visto num dispositivo real.

## Como reportar

Mesmo padrão do roteiro da v1.0: "F10.7 falhou" mais o que apareceu na tela e,
quando houver, a linha do terminal do `tauri dev`. A coluna "onde olhar" existe
para o reporte já vir com o lugar provável.
