//! Motor de STT local — whisper.cpp rodando em CPU via binding `whisper-rs`.
//!
//! Decisoes aprovadas em `docs/stt-desktop-design.md` (secoes 8/9), que este
//! modulo implementa sem reabrir:
//!
//! - **CPU, nunca GPU**: os 6 GB de VRAM ja pertencem ao LLM local (hermes3:8b
//!   via Ollama). O crate e compilado sem nenhuma feature de GPU e `use_gpu`
//!   ainda e desligado explicitamente, para nao depender do default do crate.
//! - **Modelo fora do repositorio**: o ggml oficial (~466 MB no small) e
//!   baixado no primeiro uso para o diretorio de dados do app, com validacao
//!   de SHA-256 contra os checksums publicados no repositorio oficial de
//!   modelos do whisper.cpp (Hugging Face, `ggerganov/whisper.cpp`).
//! - **Modelo trocavel sem recompilar**: todos os comandos aceitam o nome do
//!   modelo em runtime (`small` e o padrao; `base` e o plano B de latencia).
//! - **Contexto carregado uma vez**: o `WhisperContext` fica em estado
//!   gerenciado do Tauri e e reutilizado entre falas; so recarrega se o
//!   modelo pedido mudar.
//! - **`language: "pt"` fixado**: o idioma do Shogun e fixo por identidade —
//!   sem deteccao automatica, o que tambem poupa latencia.
//!
//! Erros: nenhum texto cru de biblioteca chega ao TS. Cada falha vira um
//! `ErroStt { tipo, mensagem }` com mensagem em portugues sem acentos e SEM
//! caminho de disco ou username (precedente do `_DETALHE_FALHA_PROVEDOR` no
//! servidor: erro cru nao sai). O detalhe cru vai para o stderr do processo,
//! onde so o desenvolvedor ve.

use std::io::Write as _;
use std::path::PathBuf;
use std::sync::{Arc, Mutex};

use serde::Serialize;
use sha2::{Digest, Sha256};
use tauri::{AppHandle, Emitter, Manager, State};
use whisper_rs::{FullParams, SamplingStrategy, WhisperContext, WhisperContextParameters};

/// Evento emitido durante o download do modelo. O wrapper TS escuta este nome.
pub const EVENTO_PROGRESSO_DOWNLOAD: &str = "stt-download-progresso";

/// Taxa de amostragem que o whisper.cpp exige — o contrato do PCM recebido.
const TAXA_AMOSTRAGEM_HZ: usize = 16_000;

/// O whisper.cpp precisa de pelo menos ~1 s de audio; falas mais curtas sao
/// completadas com silencio ate este tamanho (1,1 s) em vez de falhar.
const MINIMO_AMOSTRAS: usize = TAXA_AMOSTRAGEM_HZ + TAXA_AMOSTRAGEM_HZ / 10;

/// Um modelo ggml oficial do whisper.cpp que este motor sabe baixar.
///
/// URLs e checksums do repositorio oficial de modelos
/// (`huggingface.co/ggerganov/whisper.cpp`); SHA-256 conferidos contra a API
/// do Hugging Face (oid LFS) em 2026-09-13.
struct ModeloConhecido {
    nome: &'static str,
    arquivo: &'static str,
    url: &'static str,
    sha256: &'static str,
    tamanho_bytes: u64,
}

const MODELOS: &[ModeloConhecido] = &[
    ModeloConhecido {
        nome: "tiny",
        arquivo: "ggml-tiny.bin",
        url: "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.bin",
        sha256: "be07e048e1e599ad46341c8d2a135645097a538221678b7acdd1b1919c6e1b21",
        tamanho_bytes: 77_691_713,
    },
    ModeloConhecido {
        nome: "base",
        arquivo: "ggml-base.bin",
        url: "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin",
        sha256: "60ed5bc3dd14eea856493d334349b405782ddcaf0028d4b5df4088345fba2efe",
        tamanho_bytes: 147_951_465,
    },
    ModeloConhecido {
        nome: "small",
        arquivo: "ggml-small.bin",
        url: "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin",
        sha256: "1be3a9b2063867b937e64e2ec7483364a79917e157fa98c5d94b5c1fffea987b",
        tamanho_bytes: 487_601_967,
    },
    ModeloConhecido {
        nome: "medium",
        arquivo: "ggml-medium.bin",
        url: "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-medium.bin",
        sha256: "6c14d5adee5f86394037b4e4e8b59f1673b6cee10e3cf0b11bbdbee79c156208",
        tamanho_bytes: 1_533_763_059,
    },
];

/// O candidato aprovado: qualidade/custo para pt. `base` e o plano B.
const MODELO_PADRAO: &str = "small";

/// Erro estruturado devolvido aos comandos — e o contrato de erro com o TS.
///
/// `tipo` permite ao wrapper decidir a reacao sem pattern-matching na
/// mensagem (mesmo desenho do `TipoErro` em `lib/api.ts`); `mensagem` e
/// exibivel ao usuario: portugues sem acentos, sem caminho e sem username.
#[derive(Debug, Clone, Serialize)]
pub struct ErroStt {
    pub tipo: &'static str,
    pub mensagem: String,
}

impl ErroStt {
    fn novo(tipo: &'static str, mensagem: impl Into<String>) -> Self {
        Self {
            tipo,
            mensagem: mensagem.into(),
        }
    }
}

/// Situacao de um modelo no disco — resposta de `stt_modelo_status` e de
/// `stt_baixar_modelo`.
#[derive(Debug, Clone, Serialize)]
pub struct StatusModelo {
    pub modelo: String,
    pub arquivo: String,
    /// Presente E com o tamanho esperado — um download truncado conta como
    /// ausente, para o TS oferecer baixar de novo.
    pub presente: bool,
    pub tamanho_bytes: Option<u64>,
    pub tamanho_esperado_bytes: u64,
}

/// Payload do `EVENTO_PROGRESSO_DOWNLOAD`.
#[derive(Debug, Clone, Serialize)]
struct ProgressoDownload {
    modelo: String,
    baixado_bytes: u64,
    total_bytes: u64,
}

/// Contexto whisper carregado, com o nome do modelo que ele representa —
/// pedir outro modelo forca recarga; pedir o mesmo reutiliza.
struct MotorCarregado {
    modelo: String,
    contexto: Arc<WhisperContext>,
}

/// Estado gerenciado do Tauri. O `Mutex` nunca e segurado atraves de um
/// `await`: os comandos copiam o `Arc` para fora e soltam o lock antes do
/// trabalho pesado.
#[derive(Default)]
pub struct EstadoStt {
    motor: Mutex<Option<MotorCarregado>>,
}

/// Resolve o nome pedido (ou o padrao) para a entrada da tabela de modelos.
fn modelo_conhecido(nome: Option<&str>) -> Result<&'static ModeloConhecido, ErroStt> {
    let nome = nome.unwrap_or(MODELO_PADRAO);
    MODELOS.iter().find(|m| m.nome == nome).ok_or_else(|| {
        ErroStt::novo(
            "modelo_desconhecido",
            format!(
                "Modelo de voz \"{nome}\" nao e conhecido. Os disponiveis sao: tiny, base, small e medium."
            ),
        )
    })
}

/// Diretorio dos modelos: `{app_data_dir}/modelos-stt`. Criado sob demanda.
fn dir_modelos(app: &AppHandle) -> Result<PathBuf, ErroStt> {
    let base = app.path().app_data_dir().map_err(|e| {
        eprintln!("[shogun] stt: app_data_dir indisponivel: {e}");
        ErroStt::novo(
            "motor",
            "Nao consegui localizar o diretorio de dados do aplicativo.",
        )
    })?;
    let dir = base.join("modelos-stt");
    std::fs::create_dir_all(&dir).map_err(|e| {
        eprintln!("[shogun] stt: criar dir de modelos falhou: {e}");
        ErroStt::novo(
            "motor",
            "Nao consegui criar o diretorio de modelos de voz no disco.",
        )
    })?;
    Ok(dir)
}

/// Monta o `StatusModelo` olhando o arquivo no disco. Tamanho diferente do
/// esperado = download interrompido ou arquivo alheio: conta como ausente.
fn status_no_disco(app: &AppHandle, m: &'static ModeloConhecido) -> Result<StatusModelo, ErroStt> {
    let caminho = dir_modelos(app)?.join(m.arquivo);
    let tamanho = std::fs::metadata(&caminho).ok().map(|md| md.len());
    Ok(StatusModelo {
        modelo: m.nome.to_string(),
        arquivo: m.arquivo.to_string(),
        presente: tamanho == Some(m.tamanho_bytes),
        tamanho_bytes: tamanho,
        tamanho_esperado_bytes: m.tamanho_bytes,
    })
}

/// Verifica a presenca (e integridade de tamanho) de um modelo no disco.
#[tauri::command]
pub fn stt_modelo_status(
    app: AppHandle,
    modelo: Option<String>,
) -> Result<StatusModelo, ErroStt> {
    let m = modelo_conhecido(modelo.as_deref())?;
    status_no_disco(&app, m)
}

/// Baixa o modelo ggml oficial, validando o SHA-256 — primeiro uso ou
/// re-download apos falha. Idempotente: com o arquivo integro no disco,
/// devolve o status sem tocar na rede.
///
/// Progresso sai pelo evento `stt-download-progresso` (payload:
/// `{ modelo, baixado_bytes, total_bytes }`), que o TS escuta enquanto o
/// `invoke` esta pendente.
#[tauri::command]
pub async fn stt_baixar_modelo(
    app: AppHandle,
    modelo: Option<String>,
) -> Result<StatusModelo, ErroStt> {
    let m = modelo_conhecido(modelo.as_deref())?;

    // Ja esta integro? Nada a fazer — e o que torna o comando chamavel
    // "sempre antes de usar" sem custo.
    let atual = status_no_disco(&app, m)?;
    if atual.presente {
        return Ok(atual);
    }

    let dir = dir_modelos(&app)?;
    let destino = dir.join(m.arquivo);
    // Sufixo proprio ate a integridade ser confirmada: um download pela
    // metade nunca ocupa o nome final.
    let parcial = dir.join(format!("{}.baixando", m.arquivo));

    let cliente = reqwest::Client::builder()
        .connect_timeout(std::time::Duration::from_secs(15))
        .build()
        .map_err(|e| {
            eprintln!("[shogun] stt: montar cliente http falhou: {e}");
            ErroStt::novo("download", "Nao consegui preparar o download do modelo de voz.")
        })?;

    let mut resposta = cliente.get(m.url).send().await.map_err(|e| {
        eprintln!("[shogun] stt: GET do modelo falhou: {e}");
        ErroStt::novo(
            "download",
            "Nao consegui conectar ao servidor de modelos (huggingface.co). \
             Confira a conexao com a internet e tente de novo.",
        )
    })?;

    if !resposta.status().is_success() {
        return Err(ErroStt::novo(
            "download",
            format!(
                "O servidor de modelos respondeu HTTP {} ao baixar o {}.",
                resposta.status().as_u16(),
                m.nome
            ),
        ));
    }

    let total = resposta.content_length().unwrap_or(m.tamanho_bytes);
    let mut arquivo = std::fs::File::create(&parcial).map_err(|e| {
        eprintln!("[shogun] stt: criar arquivo parcial falhou: {e}");
        ErroStt::novo("download", "Nao consegui criar o arquivo do modelo no disco.")
    })?;

    let mut hasher = Sha256::new();
    let mut baixado: u64 = 0;
    let mut ultimo_reporte: u64 = 0;

    loop {
        let pedaco = match resposta.chunk().await {
            Ok(Some(p)) => p,
            Ok(None) => break,
            Err(e) => {
                eprintln!("[shogun] stt: download interrompido: {e}");
                let _ = std::fs::remove_file(&parcial);
                return Err(ErroStt::novo(
                    "download",
                    "O download do modelo foi interrompido no meio. \
                     Confira a conexao e tente de novo.",
                ));
            }
        };
        hasher.update(&pedaco);
        if let Err(e) = arquivo.write_all(&pedaco) {
            eprintln!("[shogun] stt: gravar modelo falhou: {e}");
            let _ = std::fs::remove_file(&parcial);
            return Err(ErroStt::novo(
                "download",
                "Falha ao gravar o modelo no disco — confira o espaco livre.",
            ));
        }
        baixado += pedaco.len() as u64;

        // Reporta a cada ~4 MB: granular o bastante para uma barra de
        // progresso, sem inundar o IPC.
        if baixado - ultimo_reporte >= 4 * 1024 * 1024 {
            ultimo_reporte = baixado;
            let _ = app.emit(
                EVENTO_PROGRESSO_DOWNLOAD,
                ProgressoDownload {
                    modelo: m.nome.to_string(),
                    baixado_bytes: baixado,
                    total_bytes: total,
                },
            );
        }
    }
    // Flush final + o ultimo evento (100%), que uma UI de progresso espera.
    if let Err(e) = arquivo.flush() {
        eprintln!("[shogun] stt: flush do modelo falhou: {e}");
        let _ = std::fs::remove_file(&parcial);
        return Err(ErroStt::novo(
            "download",
            "Falha ao gravar o modelo no disco — confira o espaco livre.",
        ));
    }
    drop(arquivo);
    let _ = app.emit(
        EVENTO_PROGRESSO_DOWNLOAD,
        ProgressoDownload {
            modelo: m.nome.to_string(),
            baixado_bytes: baixado,
            total_bytes: total,
        },
    );

    let hash = format!("{:x}", hasher.finalize());
    if hash != m.sha256 {
        eprintln!(
            "[shogun] stt: sha256 divergente no {} (esperado {}, veio {hash})",
            m.nome, m.sha256
        );
        let _ = std::fs::remove_file(&parcial);
        return Err(ErroStt::novo(
            "integridade",
            "O arquivo baixado nao passou na verificacao de integridade e foi \
             descartado. Tente baixar de novo.",
        ));
    }

    // Windows: rename falha se o destino existir — remove antes (se um
    // arquivo invalido estiver la, ele ja foi julgado ausente pelo status).
    if destino.exists() {
        let _ = std::fs::remove_file(&destino);
    }
    std::fs::rename(&parcial, &destino).map_err(|e| {
        eprintln!("[shogun] stt: renomear modelo falhou: {e}");
        let _ = std::fs::remove_file(&parcial);
        ErroStt::novo("download", "Falha ao finalizar o arquivo do modelo no disco.")
    })?;

    status_no_disco(&app, m)
}

/// Carrega o contexto whisper do arquivo do modelo (operacao pesada — sempre
/// chamada dentro de `spawn_blocking`).
fn carregar_contexto(caminho: &PathBuf) -> Result<WhisperContext, ErroStt> {
    let caminho_str = caminho.to_str().ok_or_else(|| {
        ErroStt::novo("motor", "O caminho do modelo contem caracteres invalidos.")
    })?;
    let mut params = WhisperContextParameters::default();
    // CPU por decisao de desenho, nao por default de crate: a VRAM e do LLM.
    params.use_gpu(false);
    WhisperContext::new_with_params(caminho_str, params).map_err(|e| {
        eprintln!("[shogun] stt: carregar modelo falhou: {e}");
        ErroStt::novo(
            "motor",
            "Nao consegui carregar o modelo de voz — o arquivo pode estar \
             corrompido. Baixe o modelo de novo.",
        )
    })
}

/// Transcreve PCM 16 kHz mono (f32, -1.0..1.0) para texto em portugues.
///
/// O contexto e carregado na primeira chamada e reutilizado nas seguintes;
/// trocar o `modelo` forca recarga. A inferencia roda em `spawn_blocking`
/// para nunca travar o runtime do Tauri.
#[tauri::command]
pub async fn stt_transcrever(
    app: AppHandle,
    estado: State<'_, EstadoStt>,
    pcm: Vec<f32>,
    modelo: Option<String>,
) -> Result<String, ErroStt> {
    if pcm.is_empty() {
        return Err(ErroStt::novo(
            "audio",
            "Nenhum audio chegou ao motor de voz — a gravacao veio vazia.",
        ));
    }

    let m = modelo_conhecido(modelo.as_deref())?;

    let status = status_no_disco(&app, m)?;
    if !status.presente {
        return Err(ErroStt::novo(
            "modelo_ausente",
            format!(
                "O modelo de voz \"{}\" ainda nao foi baixado. \
                 Baixe o modelo antes de usar o microfone.",
                m.nome
            ),
        ));
    }

    // Reutiliza o contexto ja carregado se for do mesmo modelo. O lock e
    // solto antes de qualquer await.
    let contexto = {
        let motor = estado.motor.lock().expect("mutex do motor envenenado");
        motor
            .as_ref()
            .filter(|c| c.modelo == m.nome)
            .map(|c| Arc::clone(&c.contexto))
    };
    let contexto = match contexto {
        Some(c) => c,
        None => {
            let caminho = dir_modelos(&app)?.join(m.arquivo);
            let novo = tauri::async_runtime::spawn_blocking(move || carregar_contexto(&caminho))
                .await
                .map_err(|e| {
                    eprintln!("[shogun] stt: task de carga do modelo caiu: {e}");
                    ErroStt::novo("motor", "O carregamento do modelo de voz falhou.")
                })??;
            let novo = Arc::new(novo);
            let mut motor = estado.motor.lock().expect("mutex do motor envenenado");
            *motor = Some(MotorCarregado {
                modelo: m.nome.to_string(),
                contexto: Arc::clone(&novo),
            });
            novo
        }
    };

    // Falas mais curtas que ~1 s ganham silencio ao final: o whisper.cpp
    // recusa audio abaixo de 1 s, e um "sim" rapido nao pode virar erro.
    let mut amostras = pcm;
    if amostras.len() < MINIMO_AMOSTRAS {
        amostras.resize(MINIMO_AMOSTRAS, 0.0);
    }

    tauri::async_runtime::spawn_blocking(move || {
        let mut sessao = contexto.create_state().map_err(|e| {
            eprintln!("[shogun] stt: criar estado do whisper falhou: {e}");
            ErroStt::novo("motor", "O motor de voz falhou ao preparar a transcricao.")
        })?;

        let mut params = FullParams::new(SamplingStrategy::Greedy { best_of: 1 });
        // pt fixado por identidade do Shogun — sem deteccao de idioma.
        params.set_language(Some("pt"));
        params.set_translate(false);
        // Cada fala e um comando independente; sem contexto entre chamadas.
        params.set_no_context(true);
        // Threads: os nucleos da maquina, com teto — acima de 8 o ganho do
        // ggml e marginal e a maquina inteira sentiria.
        let nucleos = std::thread::available_parallelism()
            .map(|n| n.get())
            .unwrap_or(4);
        params.set_n_threads(nucleos.min(8) as i32);
        // Nada de log do whisper.cpp no meio do stdout do app.
        params.set_print_special(false);
        params.set_print_progress(false);
        params.set_print_realtime(false);
        params.set_print_timestamps(false);
        params.set_suppress_blank(true);

        sessao.full(params, &amostras).map_err(|e| {
            eprintln!("[shogun] stt: transcricao falhou: {e}");
            ErroStt::novo("motor", "O motor de voz falhou ao transcrever o audio.")
        })?;

        let mut texto = String::new();
        for i in 0..sessao.full_n_segments() {
            if let Some(segmento) = sessao.get_segment(i) {
                match segmento.to_str_lossy() {
                    Ok(s) => texto.push_str(&s),
                    Err(e) => {
                        eprintln!("[shogun] stt: segmento ilegivel: {e}");
                    }
                }
            }
        }
        Ok(texto.trim().to_string())
    })
    .await
    .map_err(|e| {
        eprintln!("[shogun] stt: task de transcricao caiu: {e}");
        ErroStt::novo("motor", "A transcricao foi interrompida de forma inesperada.")
    })?
}
