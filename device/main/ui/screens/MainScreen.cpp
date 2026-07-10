#include "MainScreen.h"
#include "app/Session.h"
#include "esp_log.h"
#include <cstring>

static const char* TAG = "MainScreen";

// Color palette (RGB565-compatible via lv_color_hex)
static const lv_color_t COLOR_BG       = lv_color_hex(0x181818);
static const lv_color_t COLOR_HEADER   = lv_color_hex(0x101010);
static const lv_color_t COLOR_GOLD     = lv_color_hex(0xD4A054);
static const lv_color_t COLOR_GREEN    = lv_color_hex(0x00E060);
static const lv_color_t COLOR_AMBER    = lv_color_hex(0xFFC040);
static const lv_color_t COLOR_PURPLE   = lv_color_hex(0xA050E0);
static const lv_color_t COLOR_RED      = lv_color_hex(0xF04040);
static const lv_color_t COLOR_TEXT     = lv_color_hex(0xE8E4DE);
static const lv_color_t COLOR_MUTED    = lv_color_hex(0x7A7570);
static const lv_color_t COLOR_PTT_IDLE = lv_color_hex(0x3A3A3A);
static const lv_color_t COLOR_PTT_ACTIVE = lv_color_hex(0x00C050);

void MainScreen::create(lv_obj_t* parent) {
    screen_ = parent;
    lv_obj_set_style_bg_color(screen_, COLOR_BG, 0);
    lv_obj_clear_flag(screen_, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_style_pad_all(screen_, 0, 0);

    // ─── Header bar (44px) — decorative only, non-interactive ────────────────
    // Containers are made non-clickable so they never intercept touches meant
    // for the buttons placed directly on the screen below.
    lv_obj_t* header = lv_obj_create(screen_);
    lv_obj_set_size(header, 320, 44);
    lv_obj_set_pos(header, 0, 0);
    lv_obj_set_style_bg_color(header, COLOR_HEADER, 0);
    lv_obj_set_style_border_width(header, 0, 0);
    lv_obj_set_style_radius(header, 0, 0);
    lv_obj_set_style_pad_all(header, 0, 0);
    lv_obj_clear_flag(header, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_clear_flag(header, LV_OBJ_FLAG_CLICKABLE);

    // Title
    lv_obj_t* title = lv_label_create(header);
    lv_label_set_text(title, "Tank");
    lv_obj_set_style_text_color(title, COLOR_GOLD, 0);
    lv_obj_set_style_text_font(title, &lv_font_montserrat_20, 0);
    lv_obj_align(title, LV_ALIGN_LEFT_MID, 12, 0);

    // Status label (center)
    status_label_ = lv_label_create(header);
    lv_label_set_text(status_label_, "");
    lv_obj_set_style_text_color(status_label_, COLOR_MUTED, 0);
    lv_obj_set_style_text_font(status_label_, &lv_font_montserrat_16, 0);
    lv_obj_align(status_label_, LV_ALIGN_CENTER, 0, 0);

    // Settings gear button — direct child of SCREEN (not header) so the
    // container can't intercept the click. Placed over the header's right edge.
    // Taps are detected by coordinates in updateHeaderButtonsFromTouch (LVGL
    // click events are unreliable on this panel — see updatePTTFromTouch), so
    // this is a plain non-clickable container used only for the glyph.
    settings_btn_ = lv_obj_create(screen_);
    lv_obj_set_size(settings_btn_, 60, 44);
    lv_obj_set_pos(settings_btn_, 260, 0);
    lv_obj_set_style_bg_opa(settings_btn_, LV_OPA_TRANSP, 0);
    lv_obj_set_style_shadow_width(settings_btn_, 0, 0);
    lv_obj_set_style_border_width(settings_btn_, 0, 0);
    lv_obj_set_style_pad_all(settings_btn_, 0, 0);
    lv_obj_clear_flag(settings_btn_, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_clear_flag(settings_btn_, LV_OBJ_FLAG_CLICKABLE);

    lv_obj_t* gear_label = lv_label_create(settings_btn_);
    lv_label_set_text(gear_label, LV_SYMBOL_SETTINGS);
    lv_obj_set_style_text_color(gear_label, COLOR_TEXT, 0);
    lv_obj_set_style_text_font(gear_label, &lv_font_montserrat_24, 0);
    lv_obj_center(gear_label);

    // New-conversation button — mirrors the gear, sits just to its left.
    // Tap detection is coordinate-based (same as PTT and gear).
    new_conv_btn_ = lv_obj_create(screen_);
    lv_obj_set_size(new_conv_btn_, 60, 44);
    lv_obj_set_pos(new_conv_btn_, 200, 0);
    lv_obj_set_style_bg_opa(new_conv_btn_, LV_OPA_TRANSP, 0);
    lv_obj_set_style_shadow_width(new_conv_btn_, 0, 0);
    lv_obj_set_style_border_width(new_conv_btn_, 0, 0);
    lv_obj_set_style_pad_all(new_conv_btn_, 0, 0);
    lv_obj_clear_flag(new_conv_btn_, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_clear_flag(new_conv_btn_, LV_OBJ_FLAG_CLICKABLE);

    lv_obj_t* new_conv_label = lv_label_create(new_conv_btn_);
    lv_label_set_text(new_conv_label, LV_SYMBOL_PLUS);
    lv_obj_set_style_text_color(new_conv_label, COLOR_TEXT, 0);
    lv_obj_set_style_text_font(new_conv_label, &lv_font_montserrat_24, 0);
    lv_obj_center(new_conv_label);

    // ─── Activity indicator (40px) — non-interactive ────────────────────────
    lv_obj_t* activity_area = lv_obj_create(screen_);
    lv_obj_set_size(activity_area, 320, 40);
    lv_obj_set_pos(activity_area, 0, 48);
    lv_obj_set_style_bg_opa(activity_area, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(activity_area, 0, 0);
    lv_obj_set_style_pad_all(activity_area, 0, 0);
    lv_obj_clear_flag(activity_area, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_clear_flag(activity_area, LV_OBJ_FLAG_CLICKABLE);

    // Colored dot
    activity_dot_ = lv_obj_create(activity_area);
    lv_obj_set_size(activity_dot_, 14, 14);
    lv_obj_set_style_radius(activity_dot_, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_bg_color(activity_dot_, COLOR_GREEN, 0);
    lv_obj_set_style_border_width(activity_dot_, 0, 0);
    lv_obj_clear_flag(activity_dot_, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_align(activity_dot_, LV_ALIGN_CENTER, -60, 0);
    lv_obj_add_flag(activity_dot_, LV_OBJ_FLAG_HIDDEN);

    // Activity text
    activity_label_ = lv_label_create(activity_area);
    lv_label_set_text(activity_label_, "");
    lv_obj_set_style_text_color(activity_label_, COLOR_MUTED, 0);
    lv_obj_set_style_text_font(activity_label_, &lv_font_montserrat_18, 0);
    lv_obj_align(activity_label_, LV_ALIGN_CENTER, 12, 0);

    // ─── PTT Button (64px) — direct child of screen ──────────────────────────
    ptt_btn_ = lv_btn_create(screen_);
    lv_obj_set_size(ptt_btn_, 300, 64);
    lv_obj_align(ptt_btn_, LV_ALIGN_BOTTOM_MID, 0, -8);
    lv_obj_set_style_bg_color(ptt_btn_, COLOR_PTT_IDLE, 0);
    lv_obj_set_style_bg_color(ptt_btn_, COLOR_PTT_ACTIVE, LV_STATE_PRESSED);
    lv_obj_set_style_radius(ptt_btn_, 12, 0);
    lv_obj_set_style_shadow_width(ptt_btn_, 0, 0);

    // PTT button events removed — ptt_pressed_ is now driven by level-based
    // touch detection in updatePTTFromTouch() (called from the touch callback).
    // LVGL edge events (PRESSED/RELEASED) were unreliable and got stuck "on".

    ptt_label_ = lv_label_create(ptt_btn_);
    lv_label_set_text(ptt_label_, "Hold to Talk");
    lv_obj_set_style_text_color(ptt_label_, COLOR_TEXT, 0);
    lv_obj_set_style_text_font(ptt_label_, &lv_font_montserrat_24, 0);
    lv_obj_center(ptt_label_);

    ESP_LOGI(TAG, "Main screen created");
}

void MainScreen::updatePTTFromTouch(bool touching, int x, int y) {
    // PTT button region: centered 300px wide (x: 10–310), 64px tall at bottom
    // with -8px offset (y: 168–232 on a 240px screen).
    // Use level-based detection: pressed = touch active AND inside PTT area.
    // This can never get stuck because it's re-evaluated every poll cycle.
    static constexpr int PTT_Y_TOP = 168;
    static constexpr int PTT_Y_BOT = 240;
    static constexpr int PTT_X_LEFT = 0;
    static constexpr int PTT_X_RIGHT = 320;

    bool in_ptt = touching &&
                  x >= PTT_X_LEFT && x <= PTT_X_RIGHT &&
                  y >= PTT_Y_TOP && y <= PTT_Y_BOT;

    ptt_pressed_ = in_ptt;
}

void MainScreen::setStatus(const char* text) {
    if (status_label_) {
        lv_label_set_text(status_label_, text);
    }
}

void MainScreen::setActivityState(int state) {
    if (!activity_dot_ || !activity_label_) return;

    switch (state) {
        case (int)Session::State::LISTENING:
            lv_obj_clear_flag(activity_dot_, LV_OBJ_FLAG_HIDDEN);
            lv_obj_set_style_bg_color(activity_dot_, COLOR_GREEN, 0);
            lv_label_set_text(activity_label_, "Listening...");
            lv_obj_set_style_text_color(activity_label_, COLOR_GREEN, 0);
            break;
        case (int)Session::State::PROCESSING:
            lv_obj_clear_flag(activity_dot_, LV_OBJ_FLAG_HIDDEN);
            lv_obj_set_style_bg_color(activity_dot_, COLOR_AMBER, 0);
            lv_label_set_text(activity_label_, "Thinking...");
            lv_obj_set_style_text_color(activity_label_, COLOR_AMBER, 0);
            break;
        case (int)Session::State::SPEAKING:
            lv_obj_clear_flag(activity_dot_, LV_OBJ_FLAG_HIDDEN);
            lv_obj_set_style_bg_color(activity_dot_, COLOR_PURPLE, 0);
            lv_label_set_text(activity_label_, "Speaking...");
            lv_obj_set_style_text_color(activity_label_, COLOR_PURPLE, 0);
            break;
        case (int)Session::State::ERROR:
            lv_obj_clear_flag(activity_dot_, LV_OBJ_FLAG_HIDDEN);
            lv_obj_set_style_bg_color(activity_dot_, COLOR_RED, 0);
            lv_label_set_text(activity_label_, "Error");
            lv_obj_set_style_text_color(activity_label_, COLOR_RED, 0);
            break;
        default:
            // READY, IDLE, CONNECTING — hide indicator
            lv_obj_add_flag(activity_dot_, LV_OBJ_FLAG_HIDDEN);
            lv_label_set_text(activity_label_, "");
            break;
    }
}

void MainScreen::setThinking(bool active) {
    if (active) {
        setActivityState((int)Session::State::PROCESSING);
    } else {
        // Processing ended — hide the indicator
        setActivityState((int)Session::State::READY);
    }
}

void MainScreen::setError(const char* text) {
    // Error text itself is not shown on screen (no text area); the red
    // activity indicator signals the error state. Details go to the log.
    (void)text;
    setActivityState((int)Session::State::ERROR);
}

void MainScreen::setPTTState(bool pressed) {
    if (!ptt_btn_ || !ptt_label_) return;
    if (pressed) {
        lv_label_set_text(ptt_label_, "Listening...");
        // Explicitly set the active color — the button no longer uses LVGL's
        // LV_STATE_PRESSED (PTT is driven by level-based touch, not LVGL events).
        lv_obj_set_style_bg_color(ptt_btn_, COLOR_PTT_ACTIVE, 0);
    } else {
        lv_label_set_text(ptt_label_, "Hold to Talk");
        lv_obj_set_style_bg_color(ptt_btn_, COLOR_PTT_IDLE, 0);
    }
}

// ─── Event callbacks ────────────────────────────────────────────────────────

void MainScreen::updateHeaderButtonsFromTouch(bool touching, int x, int y) {
    // Detect taps on the gear (x: 260-320) and new-conversation (x: 200-260)
    // header buttons (y: 0-44) by coordinates — LVGL click events are unreliable
    // on this panel (same reason PTT is level-based).
    //
    // Fire on RELEASE, not press: the request must be raised only when the
    // finger lifts. The gear triggers a screen swap, and swapping screens while
    // a touch is still down leaves LVGL's indev pointing at a deleted/inactive
    // object on the old screen and freezes the UI. Releasing first (like a real
    // click) means the swap runs with the indev idle. We latch which button the
    // press began on and fire it only if the finger lifts.
    if (touching) {
        if (!header_touch_down_) {
            header_touch_down_ = true;
            pending_header_btn_ = 0;  // 0 = none, 1 = gear, 2 = new-conversation
            if (y <= 44) {
                if (x >= 260 && x <= 320) {
                    pending_header_btn_ = 1;
                } else if (x >= 200 && x < 260) {
                    pending_header_btn_ = 2;
                }
            }
        }
    } else {
        if (header_touch_down_) {
            // Falling edge — complete the "click".
            if (pending_header_btn_ == 1) {
                settings_requested_ = true;
            } else if (pending_header_btn_ == 2) {
                new_conv_requested_ = true;
            }
            pending_header_btn_ = 0;
        }
        header_touch_down_ = false;
    }
}
