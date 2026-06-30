#pragma once

#include "lvgl.h"
#include "hal/BoardHAL.h"
#include <cstdint>

// Forward declaration
class NvsSettings;

/// Settings screen: volume +/- buttons, network info, back button.
class SettingsScreen {
public:
    /// Create all LVGL objects on the given screen.
    void create(lv_obj_t* parent);

    /// Set dependencies needed for volume control and network display.
    void setHAL(BoardHAL* hal) { hal_ = hal; }
    void setNvsSettings(NvsSettings* nvs) { nvs_ = nvs; }
    void setPlayback(class AudioPlayback* pb) { playback_ = pb; }

    /// Refresh displayed values (call when showing screen).
    void refresh();

    /// Get current volume value (for external NVS persist).
    uint8_t getVolume() const { return volume_; }

    /// Set volume (called at boot from NVS-loaded value).
    void setInitialVolume(uint8_t vol) { volume_ = vol; }

    /// Get the underlying lv_obj_t screen.
    lv_obj_t* getScreen() const { return screen_; }

    /// Set callback for back button tap.
    using BackCallback = void(*)(void* ctx);
    void onBack(BackCallback cb, void* ctx) {
        back_cb_ = cb;
        back_ctx_ = ctx;
    }

private:
    static void backCb(lv_event_t* e);
    static void volDownCb(lv_event_t* e);
    static void volUpCb(lv_event_t* e);
    void updateVolumeLabel();

    lv_obj_t* screen_ = nullptr;
    lv_obj_t* vol_label_ = nullptr;
    lv_obj_t* net_ssid_label_ = nullptr;
    lv_obj_t* net_host_label_ = nullptr;

    BoardHAL* hal_ = nullptr;
    NvsSettings* nvs_ = nullptr;
    class AudioPlayback* playback_ = nullptr;
    uint8_t volume_ = 70;

    BackCallback back_cb_ = nullptr;
    void* back_ctx_ = nullptr;
};
