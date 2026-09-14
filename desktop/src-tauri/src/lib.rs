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
        .invoke_handler(tauri::generate_handler![
            stt::stt_modelo_status,
            stt::stt_baixar_modelo,
            stt::stt_transcrever,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
