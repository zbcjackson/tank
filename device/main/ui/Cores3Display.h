#pragma once

#include "Display.h"
#include "hal/BoardHAL.h"
#include "settings/NvsSettings.h"
#include "esp_lcd_panel_io.h"
#include "esp_lcd_panel_ops.h"
#include "lvgl.h"
#include <cstdint>

// Forward declarations for screen classes
class MainScreen;
class SettingsScreen;
class CallScreen;

/// CoreS3 display implementation — 320×240 IPS LCD with capacitive touch.
/// Uses LVGL via esp_lvgl_port for rendering.
class Cores3Display : public Display {
public:
    bool init() override;
    void showStatus(const char* status) override;
    void showUserText(const char* text) override;
    void showAssistantText(const char* text) override;
    void showThinking(bool active) override;
    void showError(const char* error) override;
    void clear() override;

    /// Poll whether the PTT button is currently pressed (LVGL event-driven).
    bool pollPressed() override;

    /// Visual PTT state (delegated to MainScreen).
    void showTalkState(bool listening) override;

    /// Poll-and-clear the new-conversation button tap (delegated to MainScreen).
    bool consumeNewConversationRequest() override;

    /// Poll-and-clear the call-mode button tap (delegated to MainScreen).
    bool consumeCallModeRequest() override;

    /// Poll-and-clear the hang-up button tap (delegated to CallScreen).
    bool consumeHangupRequest() override;

    /// Set the BoardHAL pointer for volume control from settings.
    void setHAL(BoardHAL* hal) { hal_ = hal; }

    /// Set the NVS settings pointer (for settings screen).
    void setNvsSettings(NvsSettings* nvs) { nvs_ = nvs; }

    /// Set playback pointer for software volume control.
    void setPlayback(class AudioPlayback* pb) { playback_ = pb; }

    /// Navigate back to main screen (called from the settings back-button event
    /// callback, so it defers via lv_async_call).
    void showMain();

    /// Actual screen loads. loadSettingsScreen is called from the LVGL timer
    /// callback (pollSettingsFromLvglTask); loadMainScreen via lv_async_call
    /// from the back-button event callback. Both run in the LVGL task context.
    void loadSettingsScreen();
    void loadMainScreen();
    void loadCallScreen();

    /// Get current volume from settings screen (for NVS persist from uiTask).
    uint8_t getSettingsVolume() const;

    /// Check and clear volume-dirty flag (uiTask calls this to persist NVS).
    bool consumeVolumeDirty() {
        if (volume_dirty_) { volume_dirty_ = false; return true; }
        return false;
    }

    /// Poll settings-gear tap (coordinate-based flag set by the touch callback)
    /// and load settings if requested. Called only from an LVGL timer callback
    /// (LVGL task context) — the sole place lv_scr_load is safe. Public so the
    /// static timer trampoline can reach it.
    void pollSettingsFromLvglTask();

    /// Poll call-button and hang-up taps. Called from the same LVGL timer.
    void pollCallFromLvglTask();

    /// Update activity indicator state.
    void setActivityState(int state);

    /// Whether the call screen is currently active (for routing activity updates).
    bool isCallScreenActive() const { return call_screen_active_; }

    static constexpr int SCREEN_W = 320;
    static constexpr int SCREEN_H = 240;

private:
    bool initLCD();
    bool initTouch();
    bool initLVGL();

    static void touchReadCb(lv_indev_t* indev, lv_indev_data_t* data);

    // Hardware handles (stored for LVGL port)
    esp_lcd_panel_handle_t panel_handle_ = nullptr;
    esp_lcd_panel_io_handle_t io_handle_ = nullptr;
    lv_display_t* lv_display_ = nullptr;
    lv_indev_t* lv_touch_ = nullptr;

    // Screens
    MainScreen* main_screen_ = nullptr;
    SettingsScreen* settings_screen_ = nullptr;
    CallScreen* call_screen_ = nullptr;

    // HAL reference for volume control
    BoardHAL* hal_ = nullptr;

    // NVS settings
    NvsSettings* nvs_ = nullptr;

    // Audio playback for software volume
    class AudioPlayback* playback_ = nullptr;

    // Flag: volume was changed in settings, needs NVS persist from uiTask.
    volatile bool volume_dirty_ = false;

    // Flag: call screen is the active screen (for routing touch + activity).
    bool call_screen_active_ = false;

    // Flags consumed by the uiTask for audio/session logic. Set by the LVGL
    // timer when it actually navigates (so navigation and logic stay in sync).
    volatile bool call_mode_entered_ = false;
    volatile bool call_mode_exited_ = false;
};
