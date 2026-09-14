# desktop

Aplicativo desktop do Shogun — [Tauri 2](https://tauri.app) (Rust) com frontend
em React + TypeScript (Vite).

Responsabilidades (visão completa; nem tudo existe ainda):
- captura de áudio e hotkey global para acionar o assistente (a construir);
- interface para conversar com o `server/` e acompanhar os agentes (**feito**);
- reprodução da resposta em voz (a construir);
- comunicação com o `server/` — hoje via `POST /comando`; WebSocket depois.

## O que o scaffold atual faz

Dashboard com três áreas:

- **Conversa** — histórico usuário/Shogun, campo de texto e envio ao
  `POST /comando`. O `session_id` devolvido pelo servidor é persistido
  localmente e reenviado nas próximas mensagens; "Nova conversa" descarta a
  sessão. Enquanto o servidor pensa, aparece um estado de carregamento (a
  primeira resposta pode demorar, especialmente com Ollama frio).
- **Agentes** — painel de status alimentado pela ação `consultar_pendencias`.
  O refresh é **manual** (botão "Atualizar"), que envia o comando fixo
  "ver pendências dos agentes". Escolhemos manual em vez de polling porque
  cada consulta passa pelo LLM: um polling periódico gastaria chamadas sem
  ninguém olhando. Quando existir um endpoint direto de pendências, vale
  revisitar.
- **Configurações** — URL do servidor (default `http://localhost:8000`,
  editável para um IP Tailscale) e Bearer token (`SHOGUN_AUTH_TOKEN`). Nada é
  hardcoded: os valores ficam num store local do Tauri
  (`tauri-plugin-store`, arquivo `shogun.json` no diretório de dados do app),
  junto com o `session_id` corrente.

Erros são exibidos ao usuário com mensagem específica: servidor fora do ar,
token recusado (401/403) e provedor de LLM indisponível (503).

As chamadas HTTP saem pelo `tauri-plugin-http` (fetch via Rust), não pelo
fetch do webview — assim não há CORS e o servidor não precisa de
`SHOGUN_ALLOWED_ORIGINS`, seja em localhost ou via Tailscale.

Nota sobre contratos: `shared/ts/index.ts` declara os campos em camelCase
(`sessionId`), mas o JSON real do servidor (Pydantic, sem alias) é snake_case
(`session_id`). Até o contrato compartilhado ser alinhado, o desktop usa tipos
locais em `src/lib/types.ts` que espelham o fio de verdade.

## Identidade visual e animações

O redesenho segue minimalismo japonês ("ma"), na paleta "washi cru": fundo
de papel claro (`#EDE6D4`), tinta sumi para texto e para o pincel do kanji
(`#211E1A`), cinza *hai* para o secundário (`#7A7264`), e o bengara
(`#A63D2F`) reservado **exclusivamente** a erro e atenção crítica — nunca
decorativo. Tipografia como voz — o Shogun fala em Zen Old Mincho
(serifa), o usuário e os controles em Zen Kaku Gothic New. Fontes
embarcadas via fontsource, nada vem da rede.

Duas animações usam o kanji 将軍 escrito a pincel (WebM com canal alpha em
`src/assets/`, renderizados com Remotion a partir de um projeto separado,
fora deste repositório):

- **splash de abertura** — o kanji é escrito traço a traço, sustentado e
  desfeito (~5,6s); um clique pula. `src/components/Splash.tsx`;
- **wordmark vivo** — o kanji do cabeçalho é a versão condensada sendo
  escrita em loop contínuo (2,2s), o tempo todo, não só durante o
  processamento.

Com `prefers-reduced-motion`, nem o splash nem os vídeos montam.

A navegação vive numa barra lateral fina à esquerda (só ícones; expande no
hover ou foco): nova conversa, Conversa, Agentes, visualização dividida e
Configurações. Por padrão cada view ocupa a tela sozinha; o modo dividido
(chat + agentes lado a lado) é um toggle com ícone próprio na sidebar —
preferido a uma opção nas configurações por ficar visível, custar um
clique e mostrar o estado ativo no próprio ícone. Clicar em Conversa ou
Agentes com o dividido ativo volta para a view única daquele item.

Os traços do kanji vêm do projeto [KanjiVG](http://kanjivg.tagaini.net)
(Ulrich Apel), licença CC BY-SA 3.0 — atribuição obrigatória mantida aqui.

## Estrutura

```
src/
├── App.tsx               # layout do dashboard e estado principal
├── components/
│   ├── Chat.tsx          # histórico + campo de comando
│   ├── PainelAgentes.tsx # status dos agentes (refresh manual)
│   └── Configuracoes.tsx # URL do servidor + token
└── lib/
    ├── api.ts            # POST /comando + tradução de erros
    ├── config.ts         # persistência local (tauri-plugin-store)
    └── types.ts          # tipos do fio do /comando
src-tauri/                # shell Rust (plugins http e store, sem comando custom)
```

## Rodando

```bash
cd desktop
npm install
npm run tauri dev
```

Suba o `server/` antes (veja `server/README.md`) e aponte a URL e o token na
tela de configurações do app.

Build de distribuição: `npm run tauri build`.

Antes do primeiro `tauri dev`, leia a seção abaixo — desde que o `whisper-rs`
entrou, a compilação exige duas coisas que **não vêm com o rustup**.

## Pré-requisitos de build nativo

> **Isto vale só para compilar o Rust** — `npm run tauri dev` e
> `npm run tauri build`. **`npm test` (vitest) não precisa de nada disto**: a
> suíte do desktop é de módulo puro, com o plugin de shell do Tauri mockado, e
> nunca toca na toolchain Rust. Como a maior parte das tarefas do desktop é
> TypeScript coberto por vitest, dá para trabalhar bastante aqui sem montar
> este ambiente. Monte-o quando precisar rodar o app de verdade.

Base: **Node.js 20+**, **Rust (rustup)** e as
[dependências de sistema do Tauri](https://tauri.app/start/prerequisites/) —
no Windows, isso significa o **MSVC Build Tools** e o **WebView2**.

Além disso, o `src-tauri` depende de `whisper-rs` (motor de STT local, veja
`docs/stt-desktop-design.md`), e o build script dele faz duas coisas que
precisam de ferramenta externa:

1. **compila o whisper.cpp com CMake** — e o `cmake` precisa estar achável;
2. **gera os bindings com `bindgen`** — que carrega uma **libclang** em tempo
   de build.

Nenhuma das duas é instalada pelo rustup, e nenhuma delas falha com uma
mensagem que diga o que fazer. O que segue é o caminho verificado nesta
máquina, do zero.

### Checagem automática

Antes de sair instalando, rode o diagnóstico — ele não instala nada, só olha a
máquina e imprime as variáveis prontas para colar:

```bash
python scripts/checar_ambiente_desktop.py --exports
```

Sai com código 1 enquanto faltar algo. Detalhes em `scripts/README.md`.

### 1. CMake

O `cmake` **não precisa ser instalado** na maioria das máquinas Windows deste
projeto: o Visual Studio Build Tools 2022 (que você já tem, porque o Tauri
exige o MSVC) traz um embutido — ele só **não entra no PATH**. Nesta máquina
ele está em:

```
C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe
```

Duas formas de apontar para ele, ambas aceitas pelo crate `cmake` que o build
script usa:

- **variável `CMAKE`**, apontando para o executável (preferida — é cirúrgica,
  não mexe no PATH e é a que está verificada aqui);
- ou acrescentar a pasta `bin` ao `PATH`.

```powershell
# PowerShell, permanente
[Environment]::SetEnvironmentVariable("CMAKE", "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe", "User")
```

Se a máquina não tiver Visual Studio, `winget install Kitware.CMake` resolve e
já entra no PATH.

**Sintoma de CMake ausente** — o build script do `whisper-rs-sys` despeja todas
as variáveis que procurou (todas `None`) e termina assim:

```
  running: "cmake" "-Wdev" "--debug-output" "...\out\whisper.cpp" "-B" ... "-G" "Visual Studio 17 2022" ...

  thread 'main' panicked at ...\cmake-0.1.58\src\lib.rs:1132:5:

  failed to execute command: program not found
  is `cmake` not installed?
```

### 2. libclang (para o bindgen)

Esta é a que pega todo mundo: **o bindgen precisa de uma `libclang.dll`, e ela
não existe numa instalação limpa de Windows + rustup + MSVC.** O `clang` que o
MSVC traz não serve — não é a biblioteca compartilhada que o bindgen carrega.

Há dois caminhos. **O verificado nesta máquina foi o segundo**; o primeiro é o
recomendado para uma configuração permanente, mas não foi exercitado aqui
(instalar LLVM pede privilégio de administrador e ~3 GB, e essa é uma decisão
de quem é dono da máquina).

**a) LLVM de sistema — recomendado, não verificado aqui**

```powershell
winget install LLVM.LLVM   # pacote LLVM.LLVM, hoje na versão 22.1.8
[Environment]::SetEnvironmentVariable("LIBCLANG_PATH", "C:\Program Files\LLVM\bin", "User")
```

Estável e independente de Python. O custo é instalar ~3 GB de toolchain na
máquina, com admin.

**b) Wheel `libclang` do pip — o caminho verificado**

```powershell
python -m pip install libclang
[Environment]::SetEnvironmentVariable("LIBCLANG_PATH", "<site-packages>\clang\native", "User")
```

Sem admin, ~25 MB. Nesta máquina, com o Python de usuário
(`...\Programs\Python\Python314`), o caminho ficou:

```
C:\Users\<voce>\AppData\Local\Programs\Python\Python314\Lib\site-packages\clang\native
```

O jeito de descobrir o seu, sem adivinhar:

```bash
python -c "import clang, os; print(os.path.join(os.path.dirname(clang.__file__), 'native'))"
```

**A ressalva deste caminho:** ele amarra o build Rust a um `site-packages`
específico. Trocar de versão do Python, recriar o venv ou instalar a wheel num
ambiente efêmero quebra o build sem aviso — foi exatamente o que aconteceu
depois do PR #63, cujo ambiente de build saiu junto com o worktree que o criou.
Instale a wheel no **Python de usuário permanente**, nunca num venv
descartável. Se for montar esta máquina para durar, prefira o LLVM de sistema.

**Sintoma de libclang ausente:**

```
  thread 'main' panicked at ...\bindgen-0.72.1\lib.rs:616:27:
  Unable to find libclang: "couldn't find any valid shared libraries matching:
  ['clang.dll', 'libclang.dll'], set the `LIBCLANG_PATH` environment variable to
  a path where one of these files can be found (invalid: [])"
```

### Por que não dá para pular o bindgen

O `whisper-rs-sys` aceita `WHISPER_DONT_GENERATE_BINDINGS=1` para usar os
bindings pré-gerados que vêm no crate, o que dispensaria a libclang. **No
Windows isso não funciona**: os bindings do crate foram gerados no Linux, e os
asserts de layout da glibc que eles carregam não fecham com o MSVC. O resultado
é falha de compilação, não de build script:

```
error[E0080]: attempt to compute `12_usize - 16_usize`, which would overflow
   --> ...\out/bindings.rs:469:27
469 |     ["Size of _G_fpos_t"][::std::mem::size_of::<_G_fpos_t>() - 16usize];

error[E0080]: attempt to compute `208_usize - 216_usize`, which would overflow
   --> ...\out/bindings.rs:547:26
547 |     ["Size of _IO_FILE"][::std::mem::size_of::<_IO_FILE>() - 216usize];

error: could not compile `whisper-rs-sys` (lib) due to 3 previous errors
```

`_IO_FILE` e `_G_fpos_t` são tipos de glibc — eles não deveriam nem aparecer
num build MSVC. É o atalho denunciando a própria origem. Portanto: **a
libclang é obrigatória no Windows.**

### Conferindo que deu certo

```bash
cd desktop/src-tauri
cargo check
```

Deve terminar em `Finished`. Se o `whisper-rs-sys` já tiver sido compilado
antes, o build script fica em cache e o erro não reaparece mesmo com o ambiente
errado; para testar de verdade a partir do zero, force:

```bash
cargo clean -p whisper-rs-sys && cargo check
```

Verificado nesta máquina em 13/09/2026, com `dev` em `8cbd9df`: `cargo check`
limpo em ~27 s e `cargo build` em ~1 min 06 s, com `CMAKE` e `LIBCLANG_PATH`
apontados como acima.

### Isso não é validado pelo CI

O workflow (`.github/workflows/tests.yml`) roda `pytest` e `vitest`, e **nenhum
job roda `cargo`**. Uma quebra do lado Rust passa verde no CI e só aparece na
máquina de quem compilar. Registrado como lacuna conhecida em
[`docs/ROADMAP.md`](../docs/ROADMAP.md).
