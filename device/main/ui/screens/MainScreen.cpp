#include "MainScreen.h"
#include "app/Session.h"
#include "esp_log.h"
#include <cstring>
#include <cstdio>

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
    settings_btn_ = lv_btn_create(screen_);
    lv_obj_set_size(settings_btn_, 60, 44);
    lv_obj_set_pos(settings_btn_, 260, 0);
    lv_obj_set_style_bg_opa(settings_btn_, LV_OPA_TRANSP, 0);
    lv_obj_set_style_shadow_width(settings_btn_, 0, 0);
    lv_obj_set_style_border_width(settings_btn_, 0, 0);
    lv_obj_add_flag(settings_btn_, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_add_event_cb(settings_btn_, settingsCb, LV_EVENT_CLICKED, this);

    lv_obj_t* gear_label = lv_label_create(settings_btn_);
    lv_label_set_text(gear_label, LV_SYMBOL_SETTINGS);
    lv_obj_set_style_text_color(gear_label, COLOR_TEXT, 0);
    lv_obj_set_style_text_font(gear_label, &lv_font_montserrat_24, 0);
    lv_obj_center(gear_label);

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

    // ─── Text area (88px) — non-interactive ──────────────────────────────────
    lv_obj_t* text_area = lv_obj_create(screen_);
    lv_obj_set_size(text_area, 300, 88);
    lv_obj_set_pos(text_area, 10, 90);
    lv_obj_set_style_bg_opa(text_area, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(text_area, 0, 0);
    lv_obj_set_style_pad_all(text_area, 4, 0);
    lv_obj_set_scrollbar_mode(text_area, LV_SCROLLBAR_MODE_OFF);
    lv_obj_clear_flag(text_area, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_clear_flag(text_area, LV_OBJ_FLAG_CLICKABLE);

    text_label_ = lv_label_create(text_area);
    lv_label_set_long_mode(text_label_, LV_LABEL_LONG_WRAP);
    lv_obj_set_width(text_label_, 290);
    lv_label_set_text(text_label_, "");
    lv_obj_set_style_text_color(text_label_, COLOR_TEXT, 0);
    lv_obj_set_style_text_font(text_label_, &lv_font_montserrat_16, 0);

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

void MainScreen::setDebugTouch(int x, int y) {
    (void)x; (void)y;
    // Debug label removed — kept method signature for touch callback compatibility.
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

void MainScreen::setAssistantText(const char* text) {
    if (text_label_) {
        // Reset color to normal (may have been red from a prior error)
        lv_obj_set_style_text_color(text_label_, COLOR_TEXT, 0);
        lv_label_set_text(text_label_, text);
    }
}

void MainScreen::setUserText(const char* text) {
    // Show user text briefly in the text area with prefix
    if (text_label_) {
        lv_obj_set_style_text_color(text_label_, COLOR_TEXT, 0);
        char buf[256];
        snprintf(buf, sizeof(buf), "> %s", text);
        lv_label_set_text(text_label_, buf);
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
    setActivityState((int)Session::State::ERROR);
    if (text_label_) {
        lv_obj_set_style_text_color(text_label_, COLOR_RED, 0);
        lv_label_set_text(text_label_, text);
    }
}

void MainScreen::setPTTState(bool pressed) {
    if (!ptt_btn_ || !ptt_label_) return;
    if (pressed) {
        lv_label_set_text(ptt_label_, "Listening...");
    } else {
        lv_label_set_text(ptt_label_, "Hold to Talk");
    }
}

// ─── Event callbacks ────────────────────────────────────────────────────────

void MainScreen::pttPressedCb(lv_event_t* e) {
    auto* self = static_cast<MainScreen*>(lv_event_get_user_data(e));
    self->ptt_pressed_ = true;
    ESP_LOGI(TAG, "PTT pressed");
}

void MainScreen::pttReleasedCb(lv_event_t* e) {
    auto* self = static_cast<MainScreen*>(lv_event_get_user_data(e));
    self->ptt_pressed_ = false;
    ESP_LOGI(TAG, "PTT released");
}

void MainScreen::settingsCb(lv_event_t* e) {
    auto* self = static_cast<MainScreen*>(lv_event_get_user_data(e));
    if (self->settings_cb_) {
        self->settings_cb_(self->settings_ctx_);
    }
}
