mod audio;

use audio::AudioState;
use tauri::menu::{MenuBuilder, MenuItemBuilder, SubmenuBuilder};
use tauri::Manager;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_http::init())
        .manage(AudioState::new())
        .invoke_handler(tauri::generate_handler![
            audio::start_audio_capture,
            audio::stop_audio_capture,
            audio::play_audio,
            audio::stop_playback,
        ])
        .setup(|app| {
            let toggle_devtools = MenuItemBuilder::with_id("toggle_devtools", "Toggle Developer Tools")
                .accelerator("CmdOrCtrl+Shift+I")
                .build(app)?;

            let view_menu = SubmenuBuilder::new(app, "View")
                .item(&toggle_devtools)
                .build()?;

            let menu = MenuBuilder::new(app)
                .item(&view_menu)
                .build()?;

            app.set_menu(menu)?;

            // Size window to 80% of screen and center
            if let Some(monitor) = app.primary_monitor().ok().flatten() {
                let screen = monitor.size();
                let factor = monitor.scale_factor();
                let screen_w = screen.width as f64 / factor;
                let screen_h = screen.height as f64 / factor;
                let win_w = screen_w * 0.8;
                let win_h = screen_h * 0.8;
                let pos = monitor.position();
                let x = pos.x as f64 / factor + (screen_w - win_w) / 2.0;
                let y = pos.y as f64 / factor + (screen_h - win_h) / 2.0;
                if let Some(window) = app.get_webview_window("main") {
                    let _ = window.set_size(tauri::LogicalSize::new(win_w, win_h));
                    let _ = window.set_position(tauri::LogicalPosition::new(x, y));
                }
            }

            Ok(())
        })
        .on_menu_event(|app, event| {
            if event.id().as_ref() == "toggle_devtools" {
                if let Some(window) = app.get_webview_window("main") {
                    if window.is_devtools_open() {
                        window.close_devtools();
                    } else {
                        window.open_devtools();
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running Tank");
}
