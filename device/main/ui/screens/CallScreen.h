#pragma once

#include "lvgl.h"
#include <cstdint>

/// Call-mode screen: activity indicator, wave animation, hang-up button.
class CallScreen {
public:
    /// Create all LVGL objects on the given screen.
    void create(lv_obj_t* parent);

    /// Update activity indicator (state enum from Session.h).
    void setActivityState(int state);

    /// Coordinate-based hang-up button detection.
    /// @param touching true if the panel is being touched right now
    /// @param x,y raw touch coordinates (only valid when touching)
    void updateHangupFromTouch(bool touching, int x, int y);

    /// Poll-and-clear: returns true once if hang-up was tapped.
    bool consumeHangupRequest() {
        if (hangup_requested_) { hangup_requested_ = false; return true; }
        return false;
    }

    /// Get the underlying lv_obj_t screen.
    lv_obj_t* getScreen() const { return screen_; }

private:
    lv_obj_t* screen_ = nullptr;
    lv_obj_t* activity_dot_ = nullptr;
    lv_obj_t* activity_label_ = nullptr;
    lv_obj_t* wave_container_ = nullptr;
    lv_obj_t* wave_bars_[5] = {};
    lv_obj_t* hangup_btn_ = nullptr;
    lv_anim_t wave_anims_[5] = {};

    volatile bool hangup_requested_ = false;
    bool hangup_touch_down_ = false;

    void startWaveAnimation();
    void stopWaveAnimation();
};
