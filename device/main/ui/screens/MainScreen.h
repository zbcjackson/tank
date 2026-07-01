#pragma once

#include "lvgl.h"
#include <cstdint>

/// Main screen: PTT button, activity indicator, settings gear.
class MainScreen {
public:
    /// Create all LVGL objects on the given screen.
    void create(lv_obj_t* parent);

    /// Update connection status text.
    void setStatus(const char* text);

    /// Update activity indicator (state enum from Session.h).
    void setActivityState(int state);

    /// Show/hide thinking indicator.
    void setThinking(bool active);

    /// Enter error state (shows red activity indicator; text is logged only).
    void setError(const char* text);

    /// Visual PTT state (button color).
    void setPTTState(bool pressed);

    /// Level-based PTT: update pressed state from the current raw touch.
    /// @param touching true if the panel is being touched right now
    /// @param x,y raw touch coordinates (only valid when touching)
    /// Drives ptt_pressed_ directly from touch level so it can never get
    /// stuck "on" the way edge-triggered LVGL button events can.
    void updatePTTFromTouch(bool touching, int x, int y);

    /// Returns true if PTT button is currently pressed.
    bool isPTTPressed() const { return ptt_pressed_; }

    /// Get the underlying lv_obj_t screen.
    lv_obj_t* getScreen() const { return screen_; }

    /// Set callback for settings gear tap.
    using SettingsCallback = void(*)(void* ctx);
    void onSettingsTap(SettingsCallback cb, void* ctx) {
        settings_cb_ = cb;
        settings_ctx_ = ctx;
    }

private:
    static void settingsCb(lv_event_t* e);

    lv_obj_t* screen_ = nullptr;
    lv_obj_t* status_label_ = nullptr;
    lv_obj_t* activity_dot_ = nullptr;
    lv_obj_t* activity_label_ = nullptr;
    lv_obj_t* ptt_btn_ = nullptr;
    lv_obj_t* ptt_label_ = nullptr;
    lv_obj_t* settings_btn_ = nullptr;

    volatile bool ptt_pressed_ = false;

    SettingsCallback settings_cb_ = nullptr;
    void* settings_ctx_ = nullptr;
};
