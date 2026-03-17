mod audio;

use audio::AudioState;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(AudioState::new())
        .invoke_handler(tauri::generate_handler![
            audio::start_audio_capture,
            audio::stop_audio_capture,
            audio::play_audio,
            audio::stop_playback,
        ])
        .run(tauri::generate_context!())
        .expect("error while running Tank");
}
