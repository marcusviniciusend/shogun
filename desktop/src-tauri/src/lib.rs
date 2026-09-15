mod microfone;
mod stt;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_http::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_store::Builder::new().build())
        // Motor de STT: o WhisperContext vive aqui, carregado uma vez e
        // reutilizado entre falas (ver src/stt.rs).
        .manage(stt::EstadoStt::default())
        // Captura nativa: a gravacao em andamento (o Stream do cpal e o
        // buffer que o callback de audio alimenta) vive aqui, para que o PCM
        // nunca precise atravessar o IPC (ver src/microfone.rs).
        .manage(microfone::EstadoMicrofone::default())
        .invoke_handler(tauri::generate_handler![
            stt::stt_modelo_status,
            stt::stt_baixar_modelo,
            microfone::microfone_iniciar,
            microfone::microfone_parar_e_transcrever,
            microfone::microfone_cancelar,
            microfone::microfone_nivel,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
