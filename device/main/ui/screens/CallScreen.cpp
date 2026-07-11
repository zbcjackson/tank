#include "CallScreen.h"
#include "app/Session.h"
#include "esp_log.h"

static const char* TAG = "CallScreen";

// Color palette (same as MainScreen)
static const lv_color_t COLOR_BG       = lv_color_hex(0x181818);
static const lv_color_t COLOR_GREEN    = lv_color_hex(0x00E060);
static const lv_color_t COLOR_AMBER    = lv_color_hex(0xFFC040);
static const lv_color_t COLOR_PURPLE   = lv_color_hex(0xA050E0);
static const lv_color_t COLOR_RED      = lv_color_hex(0xF04040);
static const lv_color_t COLOR_TEXT     = lv_color_hex(0xE8E4DE);
static const lv_color_t COLOR_MUTED    = lv_color_hex(0x7A7570);
static const lv_color_t COLOR_HANGUP   = lv_color_hex(0xE02020);

// Wave bar animation callback — sets bar height.
static void wave_bar_anim_cb(void* obj, int32_t v) {
    lv_obj_set_height(static_cast<lv_obj_t*>(obj), v);
}

void CallScreen::create(lv_obj_t* parent) {
    screen_ = parent;
    lv_obj_set_style_bg_color(screen_, COLOR_BG, 0);
    lv_obj_clear_flag(screen_, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_style_pad_all(screen_, 0, 0);

    // ─── Activity indicator (top area) ──────────────────────────────────────
    lv_obj_t* activity_area = lv_obj_create(screen_);
    lv_obj_set_size(activity_area, 320, 50);
    lv_obj_set_pos(activity_area, 0, 30);
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

    // Activity text
    activity_label_ = lv_label_create(activity_area);
    lv_label_set_text(activity_label_, "Listening...");
    lv_obj_set_style_text_color(activity_label_, COLOR_GREEN, 0);
    lv_obj_set_style_text_font(activity_label_, &lv_font_montserrat_20, 0);
    lv_obj_align(activity_label_, LV_ALIGN_CENTER, 12, 0);

    // ─── Wave animation (center) ────────────────────────────────────────────
    wave_container_ = lv_obj_create(screen_);
    lv_obj_set_size(wave_container_, 200, 60);
    lv_obj_align(wave_container_, LV_ALIGN_CENTER, 0, -10);
    lv_obj_set_style_bg_opa(wave_container_, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(wave_container_, 0, 0);
    lv_obj_set_style_pad_all(wave_container_, 0, 0);
    lv_obj_clear_flag(wave_container_, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_clear_flag(wave_container_, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_set_flex_flow(wave_container_, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(wave_container_, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_END, LV_FLEX_ALIGN_CENTER);
    lv_obj_set_style_pad_column(wave_container_, 12, 0);

    // Create 5 wave bars
    for (int i = 0; i < 5; i++) {
        wave_bars_[i] = lv_obj_create(wave_container_);
        lv_obj_set_size(wave_bars_[i], 8, 10);
        lv_obj_set_style_radius(wave_bars_[i], 4, 0);
        lv_obj_set_style_bg_color(wave_bars_[i], COLOR_PURPLE, 0);
        lv_obj_set_style_border_width(wave_bars_[i], 0, 0);
        lv_obj_clear_flag(wave_bars_[i], LV_OBJ_FLAG_CLICKABLE);
        lv_obj_clear_flag(wave_bars_[i], LV_OBJ_FLAG_SCROLLABLE);
    }
    // Wave hidden initially (shown only during SPEAKING)
    lv_obj_add_flag(wave_container_, LV_OBJ_FLAG_HIDDEN);

    // ─── Hang-up button (bottom center) ─────────────────────────────────────
    hangup_btn_ = lv_obj_create(screen_);
    lv_obj_set_size(hangup_btn_, 72, 72);
    lv_obj_align(hangup_btn_, LV_ALIGN_BOTTOM_MID, 0, -30);
    lv_obj_set_style_radius(hangup_btn_, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_bg_color(hangup_btn_, COLOR_HANGUP, 0);
    lv_obj_set_style_border_width(hangup_btn_, 0, 0);
    lv_obj_set_style_shadow_width(hangup_btn_, 0, 0);
    lv_obj_clear_flag(hangup_btn_, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_clear_flag(hangup_btn_, LV_OBJ_FLAG_CLICKABLE);

    // Phone-down icon (use a simple X or the CLOSE symbol)
    lv_obj_t* hangup_icon = lv_label_create(hangup_btn_);
    lv_label_set_text(hangup_icon, LV_SYMBOL_CALL);
    lv_obj_set_style_text_color(hangup_icon, COLOR_TEXT, 0);
    lv_obj_set_style_text_font(hangup_icon, &lv_font_montserrat_28, 0);
    lv_obj_center(hangup_icon);

    ESP_LOGI(TAG, "Call screen created");
}

void CallScreen::setActivityState(int state) {
    if (!activity_dot_ || !activity_label_) return;

    switch (state) {
        case (int)Session::State::LISTENING:
            lv_obj_set_style_bg_color(activity_dot_, COLOR_GREEN, 0);
            lv_label_set_text(activity_label_, "Listening...");
            lv_obj_set_style_text_color(activity_label_, COLOR_GREEN, 0);
            lv_obj_add_flag(wave_container_, LV_OBJ_FLAG_HIDDEN);
            stopWaveAnimation();
            break;
        case (int)Session::State::PROCESSING:
            lv_obj_set_style_bg_color(activity_dot_, COLOR_AMBER, 0);
            lv_label_set_text(activity_label_, "Thinking...");
            lv_obj_set_style_text_color(activity_label_, COLOR_AMBER, 0);
            lv_obj_add_flag(wave_container_, LV_OBJ_FLAG_HIDDEN);
            stopWaveAnimation();
            break;
        case (int)Session::State::SPEAKING:
            lv_obj_set_style_bg_color(activity_dot_, COLOR_PURPLE, 0);
            lv_label_set_text(activity_label_, "Speaking...");
            lv_obj_set_style_text_color(activity_label_, COLOR_PURPLE, 0);
            lv_obj_clear_flag(wave_container_, LV_OBJ_FLAG_HIDDEN);
            startWaveAnimation();
            break;
        case (int)Session::State::ERROR:
            lv_obj_set_style_bg_color(activity_dot_, COLOR_RED, 0);
            lv_label_set_text(activity_label_, "Error");
            lv_obj_set_style_text_color(activity_label_, COLOR_RED, 0);
            lv_obj_add_flag(wave_container_, LV_OBJ_FLAG_HIDDEN);
            stopWaveAnimation();
            break;
        default:
            lv_obj_set_style_bg_color(activity_dot_, COLOR_GREEN, 0);
            lv_label_set_text(activity_label_, "Listening...");
            lv_obj_set_style_text_color(activity_label_, COLOR_GREEN, 0);
            lv_obj_add_flag(wave_container_, LV_OBJ_FLAG_HIDDEN);
            stopWaveAnimation();
            break;
    }
}

void CallScreen::startWaveAnimation() {
    // Animate each bar with staggered timing to create a wave effect.
    // Heights oscillate between 10px and 50px.
    static const uint32_t delays[5] = {0, 120, 240, 360, 480};

    for (int i = 0; i < 5; i++) {
        lv_anim_init(&wave_anims_[i]);
        lv_anim_set_var(&wave_anims_[i], wave_bars_[i]);
        lv_anim_set_exec_cb(&wave_anims_[i], wave_bar_anim_cb);
        lv_anim_set_values(&wave_anims_[i], 10, 50);
        lv_anim_set_duration(&wave_anims_[i], 500);
        lv_anim_set_delay(&wave_anims_[i], delays[i]);
        lv_anim_set_playback_duration(&wave_anims_[i], 500);
        lv_anim_set_repeat_count(&wave_anims_[i], LV_ANIM_REPEAT_INFINITE);
        lv_anim_start(&wave_anims_[i]);
    }
}

void CallScreen::stopWaveAnimation() {
    for (int i = 0; i < 5; i++) {
        lv_anim_delete(wave_bars_[i], wave_bar_anim_cb);
        if (wave_bars_[i]) {
            lv_obj_set_height(wave_bars_[i], 10);
        }
    }
}

void CallScreen::updateHangupFromTouch(bool touching, int x, int y) {
    // Hang-up button region: centered 72px circle at bottom.
    // Position: align BOTTOM_MID offset (0, -30) → center at (160, 240-30-36=174)
    // Hit area: x: 124–196, y: 138–210
    static constexpr int BTN_X_LEFT  = 124;
    static constexpr int BTN_X_RIGHT = 196;
    static constexpr int BTN_Y_TOP   = 138;
    static constexpr int BTN_Y_BOT   = 210;

    if (touching) {
        if (!hangup_touch_down_) {
            // Rising edge: check if inside the button
            if (x >= BTN_X_LEFT && x <= BTN_X_RIGHT &&
                y >= BTN_Y_TOP && y <= BTN_Y_BOT) {
                hangup_touch_down_ = true;
            }
        }
    } else {
        if (hangup_touch_down_) {
            // Falling edge (release) — fire the request
            hangup_requested_ = true;
        }
        hangup_touch_down_ = false;
    }
}
