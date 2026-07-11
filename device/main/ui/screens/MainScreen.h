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

    /// Coordinate-based header button taps (settings gear + new conversation).
    /// Fires on the rising edge of a touch landing inside a button's region.
    /// LVGL CLICKED events are unreliable on this panel — the same reason PTT
    /// is level-based — so the header buttons are detected by coordinates too.
    /// @param touching true if the panel is being touched right now
    /// @param x,y raw touch coordinates (only valid when touching)
    void updateHeaderButtonsFromTouch(bool touching, int x, int y);

    /// Returns true if PTT button is currently pressed.
    bool isPTTPressed() const { return ptt_pressed_; }

    /// Get the underlying lv_obj_t screen.
    lv_obj_t* getScreen() const { return screen_; }

    /// Poll-and-clear: returns true once if the new-conversation button was
    /// tapped since the last call. Mirrors Cores3Display::consumeVolumeDirty so
    /// the WebSocket send happens off the UI task.
    bool consumeNewConvRequest() {
        if (new_conv_requested_) { new_conv_requested_ = false; return true; }
        return false;
    }

    /// Poll-and-clear: returns true once if the settings gear was tapped since
    /// the last call. Consumed by Cores3Display to defer the (async) screen load
    /// out of the touch callback.
    bool consumeSettingsRequest() {
        if (settings_requested_) { settings_requested_ = false; return true; }
        return false;
    }

    /// Poll-and-clear: returns true once if the call button was tapped.
    bool consumeCallRequest() {
        if (call_requested_) { call_requested_ = false; return true; }
        return false;
    }

private:
    lv_obj_t* screen_ = nullptr;
    lv_obj_t* status_label_ = nullptr;
    lv_obj_t* activity_dot_ = nullptr;
    lv_obj_t* activity_label_ = nullptr;
    lv_obj_t* ptt_btn_ = nullptr;
    lv_obj_t* ptt_label_ = nullptr;
    lv_obj_t* settings_btn_ = nullptr;
    lv_obj_t* new_conv_btn_ = nullptr;
    lv_obj_t* call_btn_ = nullptr;

    volatile bool ptt_pressed_ = false;
    volatile bool new_conv_requested_ = false;
    volatile bool settings_requested_ = false;
    volatile bool call_requested_ = false;
    // Edge tracking for coordinate-based header taps: true while a touch that
    // began inside a header button is still down. The request fires on release
    // (finger up), so the button the press started on is latched here until then.
    bool header_touch_down_ = false;
    int pending_header_btn_ = 0;  // 0 = none, 1 = gear, 2 = new-conversation, 3 = call
};
