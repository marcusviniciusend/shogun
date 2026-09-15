//! Captura de audio NATIVA — `cpal` (WASAPI no Windows) dentro do processo
//! Rust, no lugar do `getUserMedia` do WebView2.
//!
//! ## Por que nativo
//!
//! O motor de STT ja e nativo (`stt.rs`: whisper.cpp em CPU). Capturar em
//! Rust mantem microfone e transcricao no MESMO processo e na MESMA
//! linguagem: o PCM nunca e serializado para atravessar o IPC do Tauri (uma
//! fala de 5 s em 16 kHz f32 sao ~320 KB que viravam um array JSON), e o
//! formato que o whisper.cpp exige — f32 mono 16 kHz em [-1, 1] — fica sob
//! controle direto, em vez de depender do que o AudioContext do WebView2
//! resolver entregar.
//!
//! ## O ciclo
//!
//! Quatro comandos, no molde dos de `stt.rs`:
//!
//! - `microfone_iniciar` abre o dispositivo de entrada padrao e comeca a
//!   acumular amostras (primeiro clique no botao de microfone);
//! - `microfone_parar_e_transcrever` fecha o dispositivo, reamostra o
//!   acumulado para 16 kHz e entrega direto ao motor (clique seguinte);
//! - `microfone_cancelar` fecha o dispositivo e DESCARTA o audio (o usuario
//!   desistiu, a tela trocou, o componente desmontou);
//! - `microfone_nivel` espia a captura em andamento (pico e duracao) para o
//!   medidor da UI, sem tocar no PCM.
//!
//! Parar e transcrever sao UM comando so de proposito: entre os dois passos
//! nao existe nada que o frontend possa fazer com o PCM — e a unica coisa
//! que ele poderia fazer seria justamente o que a decisao aboliu, que e ver
//! o audio. Um comando so torna a invariante "o PCM nao sai do Rust"
//! estrutural, e nao apenas uma convencao, alem de dispensar um segundo
//! lugar onde uma gravacao orfa poderia ficar guardada.
//!
//! ## A matematica
//!
//! `media_quadro` (dentro do `Acumulador`) e `reamostrar` sao a portagem
//! literal do que vivia em `desktop/src/lib/microfone.ts` (`mediaCanais`,
//! `concatenarBlocos`, `reamostrar`), com os mesmos casos de teste — a
//! camada TS morreu com a decisao, a aritmetica dela nao. A diferenca de
//! forma: o Web Audio entregava canais PLANARES (um array por canal) e o
//! cpal entrega quadros INTERCALADOS (canais lado a lado em um array so),
//! entao a media de canais virou media por quadro.
//!
//! ## Erros
//!
//! Mesmo contrato de `stt.rs`: `ErroStt { tipo, mensagem }`, mensagem em
//! portugues sem acentos, sem caminho de disco e sem nome de dispositivo (o
//! nome do microfone pode conter o nome do usuario). O detalhe cru vai para
//! o stderr do processo.

use std::sync::{Arc, Mutex};
use std::time::Duration;

use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use cpal::{Device, FromSample, SampleFormat, SizedSample, Stream, StreamConfig};
use serde::Serialize;
use tauri::{AppHandle, State};

use crate::stt::{ErroStt, EstadoStt};

/// Taxa que o whisper.cpp exige — o destino de toda reamostragem.
pub const TAXA_ALVO_HZ: u32 = 16_000;

/// Teto de duracao de UMA gravacao. Um comando falado nao chega perto disso;
/// o limite existe para que uma gravacao esquecida aberta — o risco que o
/// ciclo por clique cria, ja que nao ha botao solto para encerra-la — nao
/// encha a memoria com audio que ninguem pediu.
const MAXIMO_SEGUNDOS: u32 = 120;

/// Quanto esperar o backend de audio inicializar o fluxo antes de desistir.
/// Sem teto, um driver travado penduraria o push-to-talk para sempre.
const TEMPO_LIMITE_ABERTURA: Duration = Duration::from_secs(5);

/* ------------------------------------------------------------------ puras */

/// Media de UM quadro intercalado, ja normalizada para f32 em [-1, 1].
///
/// A divisao e sempre por `canais`, e nao pelo tamanho do quadro: amostra
/// faltando (o quadro final truncado que alguns drivers entregam) conta como
/// silencio, exatamente como o `mediaCanais` do TS tratava canal mais curto.
/// E o que evita um NaN ou um pico artificial no fim da gravacao.
pub fn media_quadro<T: Copy>(quadro: &[T], canais: usize) -> f32
where
    f32: FromSample<T>,
{
    if canais == 0 {
        return 0.0;
    }
    let mut soma = 0.0f32;
    for &amostra in quadro {
        soma += f32::from_sample_(amostra);
    }
    soma / canais as f32
}

/// Reamostra `amostras` de `taxa_origem` para `taxa_alvo`.
///
/// Portagem literal de `reamostrar` (lib/microfone.ts), inclusive nas duas
/// estrategias:
///
/// - razao INTEIRA (o caso real, 48 kHz -> 16 kHz com razao 3) decima por
///   media de blocos — a media e um passa-baixa rudimentar que segura o
///   aliasing da decimacao seca, suficiente para voz de comando. O resto que
///   nao fecha um bloco inteiro e descartado;
/// - razao FRACIONARIA (44,1 kHz -> 16 kHz) cai na interpolacao linear, que
///   tambem cobre o caso `taxa_origem < taxa_alvo`.
///
/// Taxas iguais (ou taxa invalida) devolvem copia.
pub fn reamostrar(amostras: &[f32], taxa_origem: u32, taxa_alvo: u32) -> Vec<f32> {
    if amostras.is_empty() || taxa_origem == taxa_alvo || taxa_origem == 0 || taxa_alvo == 0 {
        return amostras.to_vec();
    }
    if taxa_origem.is_multiple_of(taxa_alvo) {
        let razao = (taxa_origem / taxa_alvo) as usize;
        return amostras
            .chunks_exact(razao)
            .map(|bloco| bloco.iter().sum::<f32>() / razao as f32)
            .collect();
    }
    let razao = f64::from(taxa_origem) / f64::from(taxa_alvo);
    let tamanho = ((amostras.len() as f64 / razao).floor() as usize).max(1);
    (0..tamanho)
        .map(|i| {
            let posicao = i as f64 * razao;
            let inteiro = posicao.floor() as usize;
            let fracao = (posicao - inteiro as f64) as f32;
            let a = amostras.get(inteiro).copied().unwrap_or(0.0);
            let b = amostras.get(inteiro + 1).copied().unwrap_or(a);
            a + (b - a) * fracao
        })
        .collect()
}

/// Duracao em segundos de um PCM na taxa dada — so para log e diagnostico.
pub fn duracao_segundos(pcm: &[f32], taxa: u32) -> f32 {
    if taxa == 0 {
        return 0.0;
    }
    pcm.len() as f32 / taxa as f32
}

/// Maior amplitude absoluta do PCM; 0 significa silencio absoluto — o sinal
/// de que o microfone abriu mudo (mutado no sistema, ganho zerado).
pub fn pico_absoluto(pcm: &[f32]) -> f32 {
    pcm.iter().fold(0.0f32, |pico, a| pico.max(a.abs()))
}

/// O buffer que o callback de audio alimenta.
///
/// Faz o papel do `concatenarBlocos` do TS: la os blocos do worklet eram
/// guardados e juntados no final; aqui cada bloco ja e anexado a um PCM
/// continuo unico, com teto de tamanho.
pub struct Acumulador {
    amostras: Vec<f32>,
    limite: usize,
    /// Maior amplitude absoluta vista desde a ultima leitura do medidor.
    ///
    /// Vive aqui, e nao num evento emitido pelo callback, porque a thread de
    /// audio nao pode alocar nem fazer I/O (ver `construir_stream`): emitir
    /// evento Tauri de dentro dela faria as duas coisas. Um `max` por quadro
    /// e gratuito; quem paga o custo e a UI, perguntando quando quer.
    pico_parcial: f32,
}

impl Acumulador {
    pub fn novo(limite: usize) -> Self {
        Self {
            amostras: Vec::new(),
            limite,
            pico_parcial: 0.0,
        }
    }

    /// Amostras ja capturadas — a duracao real do que sera transcrito.
    pub fn quantidade(&self) -> usize {
        self.amostras.len()
    }

    /// Entrega o pico acumulado e zera a janela, para a proxima leitura medir
    /// so o intervalo seguinte. Sem o reset o medidor viraria uma catraca,
    /// presa no grito mais alto da gravacao inteira.
    pub fn tomar_pico(&mut self) -> f32 {
        std::mem::replace(&mut self.pico_parcial, 0.0)
    }

    /// Anexa um bloco intercalado ja mesclado para mono. Passado o teto, o
    /// excedente e ignorado (a gravacao para de crescer em vez de estourar).
    pub fn empurrar<T: Copy>(&mut self, intercalado: &[T], canais: usize)
    where
        f32: FromSample<T>,
    {
        if canais == 0 {
            return;
        }
        for quadro in intercalado.chunks(canais) {
            if self.amostras.len() >= self.limite {
                return;
            }
            let amostra = media_quadro(quadro, canais);
            self.pico_parcial = self.pico_parcial.max(amostra.abs());
            self.amostras.push(amostra);
        }
    }

    /// Entrega o PCM acumulado, deixando o acumulador vazio.
    pub fn tomar(&mut self) -> Vec<f32> {
        std::mem::take(&mut self.amostras)
    }
}

/* --------------------------------------------------------------- dispositivo */

/// Uma gravacao em andamento. Guardar o `Stream` mantem o dispositivo
/// aberto; solta-lo (Drop) fecha o fluxo e encerra a thread do backend.
struct Sessao {
    stream: Stream,
    buffer: Arc<Mutex<Acumulador>>,
    taxa_hz: u32,
}

/// Estado gerenciado do Tauri, no molde do `EstadoStt`: uma gravacao por vez,
/// atras de um `Mutex` que nunca e segurado atraves de um `await`.
#[derive(Default)]
pub struct EstadoMicrofone {
    sessao: Mutex<Option<Sessao>>,
}

/// O que o comando de inicio devolve ao frontend: a taxa e a contagem de
/// canais que o dispositivo REALMENTE entregou. Nao serve para decidir nada
/// no TS (a conversao toda acontece aqui) — serve para o indicador de
/// gravacao e para o diagnostico do roteiro manual.
#[derive(Debug, Clone, Serialize)]
pub struct InfoGravacao {
    pub taxa_hz: u32,
    pub canais: u16,
}

/// Traduz a falha do cpal numa mensagem exibivel, sem citar dispositivo.
///
/// `PermissionDenied` e o caso que o Windows produz quando a chave de
/// privacidade de microfone esta desligada — a unica falha aqui que tem
/// conserto pelo usuario, e por isso a unica que aponta o caminho exato.
fn traduzir_erro_cpal(erro: &cpal::Error, contexto: &str) -> ErroStt {
    eprintln!("[shogun] microfone: {contexto}: {erro}");
    let mensagem = match erro.kind() {
        cpal::ErrorKind::PermissionDenied => {
            "O Windows negou o acesso ao microfone. Abra Configuracoes > \
             Privacidade e seguranca > Microfone e permita que aplicativos \
             da area de trabalho usem o microfone."
        }
        cpal::ErrorKind::DeviceNotAvailable | cpal::ErrorKind::HostUnavailable => {
            "Nenhum microfone disponivel. Conecte um dispositivo de entrada e \
             tente de novo."
        }
        cpal::ErrorKind::DeviceBusy => {
            "O microfone esta em uso por outro aplicativo. Feche o outro \
             aplicativo e tente de novo."
        }
        cpal::ErrorKind::UnsupportedConfig => {
            "O microfone nao oferece nenhum formato de audio que eu saiba ler."
        }
        _ => "Nao consegui abrir o microfone.",
    };
    ErroStt::novo("microfone", mensagem)
}

/// Constroi o fluxo de entrada para um formato de amostra concreto.
///
/// O callback roda na thread de audio do backend: ele so mescla para mono e
/// anexa ao acumulador — nada de alocacao por amostra, nada de I/O. Um
/// `Mutex` envenenado (panico em outro callback) e ignorado em silencio;
/// perder audio e melhor do que derrubar a thread de audio.
fn construir_stream<T>(
    dispositivo: &Device,
    config: &StreamConfig,
    canais: usize,
    buffer: Arc<Mutex<Acumulador>>,
) -> Result<Stream, cpal::Error>
where
    T: SizedSample,
    f32: FromSample<T>,
{
    dispositivo.build_input_stream::<T, _, _>(
        *config,
        move |dados: &[T], _: &cpal::InputCallbackInfo| {
            if let Ok(mut acumulador) = buffer.lock() {
                acumulador.empurrar(dados, canais);
            }
        },
        |erro| eprintln!("[shogun] microfone: falha no fluxo de captura: {erro}"),
        Some(TEMPO_LIMITE_ABERTURA),
    )
}

/// Abre o dispositivo de entrada padrao na configuracao que ELE oferece.
///
/// Nada de pedir 16 kHz ao driver: no modo compartilhado do WASAPI a taxa e
/// a do mixer do Windows (tipicamente 44,1 ou 48 kHz) e um pedido divergente
/// so produziria uma falha a mais. A conversao para 16 kHz e trabalho do
/// `reamostrar`, no fechamento da gravacao.
fn abrir_dispositivo() -> Result<Sessao, ErroStt> {
    let host = cpal::default_host();
    let dispositivo = host.default_input_device().ok_or_else(|| {
        eprintln!("[shogun] microfone: nenhum dispositivo de entrada padrao");
        ErroStt::novo(
            "microfone",
            "Nenhum microfone foi encontrado. Conecte um dispositivo de \
             entrada e tente de novo.",
        )
    })?;

    let suportado = dispositivo
        .default_input_config()
        .map_err(|e| traduzir_erro_cpal(&e, "config padrao de entrada"))?;
    let formato = suportado.sample_format();
    let canais = suportado.channels();
    let taxa_hz = suportado.sample_rate();
    let config: StreamConfig = suportado.config();

    let limite = (taxa_hz as usize).saturating_mul(MAXIMO_SEGUNDOS as usize);
    let buffer = Arc::new(Mutex::new(Acumulador::novo(limite)));
    let canais_usize = canais as usize;

    let stream = match formato {
        SampleFormat::F32 => {
            construir_stream::<f32>(&dispositivo, &config, canais_usize, Arc::clone(&buffer))
        }
        SampleFormat::F64 => {
            construir_stream::<f64>(&dispositivo, &config, canais_usize, Arc::clone(&buffer))
        }
        SampleFormat::I8 => {
            construir_stream::<i8>(&dispositivo, &config, canais_usize, Arc::clone(&buffer))
        }
        SampleFormat::I16 => {
            construir_stream::<i16>(&dispositivo, &config, canais_usize, Arc::clone(&buffer))
        }
        SampleFormat::I32 => {
            construir_stream::<i32>(&dispositivo, &config, canais_usize, Arc::clone(&buffer))
        }
        SampleFormat::U8 => {
            construir_stream::<u8>(&dispositivo, &config, canais_usize, Arc::clone(&buffer))
        }
        SampleFormat::U16 => {
            construir_stream::<u16>(&dispositivo, &config, canais_usize, Arc::clone(&buffer))
        }
        outro => {
            eprintln!("[shogun] microfone: formato de amostra nao suportado: {outro:?}");
            return Err(ErroStt::novo(
                "microfone",
                "O microfone entrega o audio num formato que eu nao sei ler.",
            ));
        }
    }
    .map_err(|e| traduzir_erro_cpal(&e, "construir fluxo de entrada"))?;

    stream
        .play()
        .map_err(|e| traduzir_erro_cpal(&e, "iniciar fluxo de entrada"))?;

    Ok(Sessao {
        stream,
        buffer,
        taxa_hz,
    })
}

/// Fecha o dispositivo e recolhe o PCM mono na taxa do dispositivo.
fn encerrar(sessao: Sessao) -> Vec<f32> {
    let Sessao {
        stream,
        buffer,
        taxa_hz: _,
    } = sessao;
    // Soltar o Stream para o fluxo e encerra a thread do backend. Vem
    // ANTES de ler o buffer para que nenhum callback ainda esteja escrevendo.
    drop(stream);
    buffer
        .lock()
        .map(|mut acumulador| acumulador.tomar())
        .unwrap_or_default()
}

/* ------------------------------------------------------------------ comandos */

/// Abre o microfone e comeca a gravar (push-to-talk pressionado).
///
/// Devolve a taxa e os canais reais do dispositivo. Ja havendo gravacao em
/// andamento, falha como `gravacao` em vez de abrir um segundo fluxo — o
/// estado do ditado no TS ja impede isso, e aqui a garantia vira estrutural.
#[tauri::command]
pub async fn microfone_iniciar(
    estado: State<'_, EstadoMicrofone>,
) -> Result<InfoGravacao, ErroStt> {
    {
        let sessao = estado.sessao.lock().expect("mutex do microfone envenenado");
        if sessao.is_some() {
            return Err(ErroStt::novo(
                "gravacao",
                "Ja existe uma gravacao em andamento.",
            ));
        }
    }

    let nova = abrir_dispositivo()?;
    eprintln!(
        "[shogun] microfone: gravando a {} Hz (mesclado para mono)",
        nova.taxa_hz
    );
    // A contagem exposta e a do PCM que sai daqui — mono, sempre. A do
    // dispositivo fica no log, nao no contrato com o TS.
    let info = InfoGravacao {
        taxa_hz: nova.taxa_hz,
        canais: 1,
    };

    let mut guarda = estado.sessao.lock().expect("mutex do microfone envenenado");
    if guarda.is_some() {
        // Corrida entre dois `iniciar`: quem chegou depois descarta o proprio
        // fluxo em vez de sobrescrever (e vazar) o que ja estava gravando.
        drop(encerrar(nova));
        return Err(ErroStt::novo(
            "gravacao",
            "Ja existe uma gravacao em andamento.",
        ));
    }
    *guarda = Some(nova);
    Ok(info)
}

/// Fecha o microfone, converte o acumulado e transcreve (push-to-talk solto).
///
/// Este e o unico caminho do audio ate o motor: o PCM nasce no callback de
/// audio, e reamostrado aqui e entra direto no whisper — sem nunca virar
/// JSON nem cruzar o IPC.
#[tauri::command]
pub async fn microfone_parar_e_transcrever(
    app: AppHandle,
    microfone: State<'_, EstadoMicrofone>,
    stt: State<'_, EstadoStt>,
    modelo: Option<String>,
) -> Result<String, ErroStt> {
    let sessao = {
        microfone
            .sessao
            .lock()
            .expect("mutex do microfone envenenado")
            .take()
    };
    let Some(sessao) = sessao else {
        return Err(ErroStt::novo(
            "gravacao",
            "Nao havia gravacao em andamento para transcrever.",
        ));
    };

    let taxa_hz = sessao.taxa_hz;
    let bruto = encerrar(sessao);
    if bruto.is_empty() {
        return Err(ErroStt::novo(
            "audio",
            "Nenhum audio chegou do microfone — a gravacao veio vazia.",
        ));
    }

    let pcm = reamostrar(&bruto, taxa_hz, TAXA_ALVO_HZ);
    eprintln!(
        "[shogun] microfone: {} amostras a {taxa_hz} Hz -> {} a {TAXA_ALVO_HZ} Hz \
         (~{:.2}s), pico {:.3}",
        bruto.len(),
        pcm.len(),
        duracao_segundos(&pcm, TAXA_ALVO_HZ),
        pico_absoluto(&pcm),
    );

    crate::stt::transcrever_pcm(&app, stt.inner(), pcm, modelo.as_deref()).await
}

/// O que o medidor da UI precisa saber sobre a captura em andamento.
#[derive(Clone, Copy, serde::Serialize)]
pub struct NivelMicrofone {
    /// Maior amplitude absoluta (0.0..=1.0) desde a leitura anterior.
    pub pico: f32,
    /// Duracao ja capturada, em segundos.
    ///
    /// Sai da contagem de amostras, nao de um relogio do JS: e o tempo do
    /// audio que sera de fato transcrito. Um travamento da thread de audio
    /// congela este numero, que e a verdade — um cronometro de parede
    /// continuaria subindo e mentiria que esta gravando.
    pub segundos: f32,
}

/// Le o nivel da gravacao em andamento. `None` quando nao ha nenhuma.
///
/// Feito para ser chamado em laco pela UI (~15x/s): nao aloca, nao copia PCM
/// e devolve dois numeros. Ler tambem ZERA a janela do pico, entao duas
/// leituras concorrentes se roubariam — ha um consumidor so, o medidor.
#[tauri::command]
pub async fn microfone_nivel(
    estado: State<'_, EstadoMicrofone>,
) -> Result<Option<NivelMicrofone>, ErroStt> {
    let guarda = estado.sessao.lock().expect("mutex do microfone envenenado");
    let Some(sessao) = guarda.as_ref() else {
        return Ok(None);
    };
    let taxa_hz = sessao.taxa_hz;
    let (pico, amostras) = {
        let mut acumulador = sessao.buffer.lock().expect("mutex do acumulador envenenado");
        (acumulador.tomar_pico(), acumulador.quantidade())
    };
    Ok(Some(NivelMicrofone {
        pico,
        segundos: amostras as f32 / taxa_hz as f32,
    }))
}

/// Fecha o microfone DESCARTANDO o audio. Idempotente: sem gravacao em
/// andamento e um no-op silencioso, porque quem cancela (desmontagem de
/// componente, ponteiro cancelado) raramente sabe se havia algo aberto.
#[tauri::command]
pub async fn microfone_cancelar(estado: State<'_, EstadoMicrofone>) -> Result<(), ErroStt> {
    let sessao = {
        estado
            .sessao
            .lock()
            .expect("mutex do microfone envenenado")
            .take()
    };
    if let Some(sessao) = sessao {
        drop(encerrar(sessao));
    }
    Ok(())
}

/* -------------------------------------------------------------------- testes */

#[cfg(test)]
mod testes {
    use super::*;

    /// Mescla um bloco intercalado para mono pelo MESMO caminho que o
    /// callback de audio usa — nada de uma segunda implementacao so para o
    /// teste. Faz o papel do `mediaCanais` do TS nos casos abaixo.
    fn mesclar_mono<T: Copy>(intercalado: &[T], canais: usize) -> Vec<f32>
    where
        f32: FromSample<T>,
    {
        let mut acumulador = Acumulador::novo(usize::MAX);
        acumulador.empurrar(intercalado, canais);
        acumulador.tomar()
    }

    /* --- media de canais: os casos que vinham de microfone.test.ts --- */

    #[test]
    fn sem_canal_nenhum_devolve_vazio() {
        assert!(mesclar_mono::<f32>(&[0.1, 0.2], 0).is_empty());
        assert!(mesclar_mono::<f32>(&[], 1).is_empty());
    }

    #[test]
    fn um_canal_so_passa_direto() {
        let entrada = [0.1f32, -0.2, 0.3];
        assert_eq!(mesclar_mono(&entrada, 1), vec![0.1, -0.2, 0.3]);
    }

    #[test]
    fn dois_canais_viram_a_media_amostra_a_amostra() {
        // Intercalado: (E=1, D=0), (E=0, D=1), (E=-1, D=-1).
        let entrada = [1.0f32, 0.0, 0.0, 1.0, -1.0, -1.0];
        assert_eq!(mesclar_mono(&entrada, 2), vec![0.5, 0.5, -1.0]);
    }

    #[test]
    fn quadro_final_truncado_conta_como_silencio_e_nao_como_nan() {
        // Equivalente intercalado do "canal mais curto" do TS: o ultimo
        // quadro tem so um dos dois canais.
        let entrada = [1.0f32, 1.0, 1.0];
        assert_eq!(mesclar_mono(&entrada, 2), vec![1.0, 0.5]);
    }

    #[test]
    fn amostras_inteiras_sao_normalizadas_para_menos_um_a_um() {
        // i16 no extremo positivo vira ~1.0; no negativo, -1.0; o zero, 0.0.
        let entrada = [i16::MAX, 0, i16::MIN];
        let saida = mesclar_mono(&entrada, 1);
        assert!((saida[0] - 1.0).abs() < 1e-3, "veio {}", saida[0]);
        assert_eq!(saida[1], 0.0);
        assert!((saida[2] + 1.0).abs() < 1e-3, "veio {}", saida[2]);
    }

    /* --- acumulador: o que era concatenarBlocos --- */

    #[test]
    fn pico_parcial_guarda_o_maior_absoluto_e_zera_ao_ser_lido() {
        let mut acumulador = Acumulador::novo(1_000);
        acumulador.empurrar(&[0.2f32, -0.7, 0.3], 1);
        // O negativo vence: o medidor mede amplitude, nao sinal.
        assert!((acumulador.tomar_pico() - 0.7).abs() < 1e-6);
        // Ler zera a janela — sem isso o medidor ficaria preso no pico antigo.
        assert_eq!(acumulador.tomar_pico(), 0.0);
        acumulador.empurrar(&[0.1f32], 1);
        assert!((acumulador.tomar_pico() - 0.1).abs() < 1e-6);
    }

    #[test]
    fn pico_e_quantidade_nao_consomem_o_pcm() {
        let mut acumulador = Acumulador::novo(1_000);
        acumulador.empurrar(&[0.5f32, -0.5], 1);
        acumulador.tomar_pico();
        assert_eq!(acumulador.quantidade(), 2);
        // O audio segue inteiro: o medidor le, nao rouba.
        assert_eq!(acumulador.tomar(), vec![0.5, -0.5]);
    }

    #[test]
    fn silencio_absoluto_mantem_o_pico_em_zero() {
        let mut acumulador = Acumulador::novo(1_000);
        acumulador.empurrar(&[0.0f32; 64], 1);
        assert_eq!(acumulador.tomar_pico(), 0.0);
    }

    #[test]
    fn acumulador_preserva_ordem_e_conteudo_dos_blocos() {
        let mut acumulador = Acumulador::novo(1_000);
        acumulador.empurrar(&[1.0f32, 2.0], 1);
        acumulador.empurrar(&[0.0f32; 0], 1);
        acumulador.empurrar(&[3.0f32], 1);
        assert_eq!(acumulador.tomar(), vec![1.0, 2.0, 3.0]);
    }

    #[test]
    fn acumulador_vazio_devolve_vazio_e_tomar_esvazia() {
        let mut acumulador = Acumulador::novo(10);
        assert!(acumulador.tomar().is_empty());
        acumulador.empurrar(&[1.0f32], 1);
        assert_eq!(acumulador.tomar(), vec![1.0]);
        assert!(acumulador.tomar().is_empty());
    }

    #[test]
    fn acumulador_respeita_o_teto_em_vez_de_crescer_sem_limite() {
        let mut acumulador = Acumulador::novo(3);
        acumulador.empurrar(&[1.0f32, 2.0, 3.0, 4.0, 5.0], 1);
        assert_eq!(acumulador.tomar(), vec![1.0, 2.0, 3.0]);
    }

    /* --- reamostragem: os casos que vinham de microfone.test.ts --- */

    #[test]
    fn taxas_iguais_devolvem_copia() {
        let pcm = [0.1f32, 0.2];
        assert_eq!(reamostrar(&pcm, TAXA_ALVO_HZ, TAXA_ALVO_HZ), vec![0.1, 0.2]);
    }

    #[test]
    fn vazio_continua_vazio_em_qualquer_taxa() {
        assert!(reamostrar(&[], 48_000, TAXA_ALVO_HZ).is_empty());
    }

    #[test]
    fn razao_inteira_decima_por_media_de_blocos() {
        // 48 kHz -> 16 kHz, razao 3: cada trio vira sua media.
        let pcm = [0.0f32, 3.0, 3.0, 6.0, 6.0, 6.0];
        assert_eq!(reamostrar(&pcm, 48_000, 16_000), vec![2.0, 6.0]);
    }

    #[test]
    fn descarta_o_resto_que_nao_fecha_um_bloco_inteiro() {
        let pcm = [3.0f32, 3.0, 3.0, 9.0]; // razao 3: sobra 1 amostra
        assert_eq!(reamostrar(&pcm, 48_000, 16_000), vec![3.0]);
    }

    #[test]
    fn um_segundo_a_48k_vira_um_segundo_a_16k() {
        let pcm = vec![0.0f32; 48_000];
        assert_eq!(reamostrar(&pcm, 48_000, TAXA_ALVO_HZ).len(), 16_000);
    }

    #[test]
    fn razao_fracionaria_interpola_sem_inventar_amplitude() {
        // 44,1 kHz -> 16 kHz: sinal constante continua constante.
        let pcm = vec![0.5f32; 4_410];
        let saida = reamostrar(&pcm, 44_100, 16_000);
        assert_eq!(saida.len(), 1_600);
        for amostra in saida {
            assert!((amostra - 0.5).abs() < 1e-6, "veio {amostra}");
        }
    }

    #[test]
    fn taxa_de_origem_menor_interpola_para_cima_sem_quebrar() {
        // 8 kHz -> 16 kHz: posicoes 0, 0.5, 1, 1.5 sobre [0, 1].
        let saida = reamostrar(&[0.0f32, 1.0], 8_000, 16_000);
        assert_eq!(saida, vec![0.0, 0.5, 1.0, 1.0]);
    }

    #[test]
    fn taxa_zero_nao_divide_por_zero() {
        assert_eq!(reamostrar(&[0.1f32], 0, 16_000), vec![0.1]);
        assert_eq!(reamostrar(&[0.1f32], 48_000, 0), vec![0.1]);
    }

    /* --- diagnostico --- */

    #[test]
    fn duracao_e_pico() {
        assert_eq!(duracao_segundos(&vec![0.0; 32_000], TAXA_ALVO_HZ), 2.0);
        assert_eq!(duracao_segundos(&[0.0], 0), 0.0);
        assert!((pico_absoluto(&[0.1, -0.8, 0.3]) - 0.8).abs() < 1e-6);
        assert_eq!(pico_absoluto(&[0.0; 4]), 0.0);
        assert_eq!(pico_absoluto(&[]), 0.0);
    }
}
