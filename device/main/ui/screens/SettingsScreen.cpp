#include "SettingsScreen.h"
#include "settings/NvsSettings.h"
#include "audio/AudioPlayback.h"
#include "esp_log.h"
#include <cstdio>

static const char* TAG = "SettingsScreen";

static const lv_color_t COLOR_BG     = lv_color_hex(0x181818);
static const lv_color_t COLOR_HEADER = lv_color_hex(0x101010);
static const lv_color_t COLOR_GOLD   = lv_color_hex(0xD4A054);
static const lv_color_t COLOR_TEXT   = lv_color_hex(0xE8E4DE);
static const lv_color_t COLOR_MUTED  = lv_color_hex(0x7A7570);
static const lv_color_t COLOR_BTN    = lv_color_hex(0x3A3A3A);

void SettingsScreen::create(lv_obj_t* parent) {
    screen_ = parent;
    lv_obj_set_style_bg_color(screen_, COLOR_BG, 0);
    lv_obj_clear_flag(screen_, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_style_pad_all(screen_, 0, 0);

    // ─── Header (44px) — decorative, non-interactive ────────────────────────
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
    lv_label_set_text(title, "Settings");
    lv_obj_set_style_text_color(title, COLOR_TEXT, 0);
    lv_obj_set_style_text_font(title, &lv_font_montserrat_20, 0);
    lv_obj_align(title, LV_ALIGN_LEFT_MID, 72, 0);

    // Back button — direct child of SCREEN so the header can't intercept taps.
    lv_obj_t* back_btn = lv_btn_create(screen_);
    lv_obj_set_size(back_btn, 70, 44);
    lv_obj_set_pos(back_btn, 0, 0);
    lv_obj_set_style_bg_opa(back_btn, LV_OPA_TRANSP, 0);
    lv_obj_set_style_shadow_width(back_btn, 0, 0);
    lv_obj_set_style_border_width(back_btn, 0, 0);
    lv_obj_add_flag(back_btn, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_add_event_cb(back_btn, backCb, LV_EVENT_CLICKED, this);

    lv_obj_t* back_label = lv_label_create(back_btn);
    lv_label_set_text(back_label, LV_SYMBOL_LEFT);
    lv_obj_set_style_text_color(back_label, COLOR_TEXT, 0);
    lv_obj_set_style_text_font(back_label, &lv_font_montserrat_24, 0);
    lv_obj_center(back_label);

    // ─── Volume section label (non-interactive) ─────────────────────────────
    lv_obj_t* vol_title = lv_label_create(screen_);
    lv_label_set_text(vol_title, "Volume");
    lv_obj_set_style_text_color(vol_title, COLOR_MUTED, 0);
    lv_obj_set_style_text_font(vol_title, &lv_font_montserrat_16, 0);
    lv_obj_set_pos(vol_title, 12, 56);

    // Minus button — direct child of screen.
    lv_obj_t* vol_down = lv_btn_create(screen_);
    lv_obj_set_size(vol_down, 64, 48);
    lv_obj_set_pos(vol_down, 20, 82);
    lv_obj_set_style_bg_color(vol_down, COLOR_BTN, 0);
    lv_obj_set_style_radius(vol_down, 8, 0);
    lv_obj_add_event_cb(vol_down, volDownCb, LV_EVENT_CLICKED, this);

    lv_obj_t* minus_label = lv_label_create(vol_down);
    lv_label_set_text(minus_label, "-");
    lv_obj_set_style_text_color(minus_label, COLOR_TEXT, 0);
    lv_obj_set_style_text_font(minus_label, &lv_font_montserrat_28, 0);
    lv_obj_center(minus_label);

    // Volume percentage
    vol_label_ = lv_label_create(screen_);
    lv_label_set_text(vol_label_, "70%");
    lv_obj_set_style_text_color(vol_label_, COLOR_TEXT, 0);
    lv_obj_set_style_text_font(vol_label_, &lv_font_montserrat_24, 0);
    lv_obj_set_pos(vol_label_, 140, 94);

    // Plus button — direct child of screen.
    lv_obj_t* vol_up = lv_btn_create(screen_);
    lv_obj_set_size(vol_up, 64, 48);
    lv_obj_set_pos(vol_up, 236, 82);
    lv_obj_set_style_bg_color(vol_up, COLOR_BTN, 0);
    lv_obj_set_style_radius(vol_up, 8, 0);
    lv_obj_add_event_cb(vol_up, volUpCb, LV_EVENT_CLICKED, this);

    lv_obj_t* plus_label = lv_label_create(vol_up);
    lv_label_set_text(plus_label, "+");
    lv_obj_set_style_text_color(plus_label, COLOR_TEXT, 0);
    lv_obj_set_style_text_font(plus_label, &lv_font_montserrat_28, 0);
    lv_obj_center(plus_label);

    // ─── Network info (non-interactive labels directly on screen) ───────────
    lv_obj_t* net_title = lv_label_create(screen_);
    lv_label_set_text(net_title, "Network");
    lv_obj_set_style_text_color(net_title, COLOR_MUTED, 0);
    lv_obj_set_style_text_font(net_title, &lv_font_montserrat_16, 0);
    lv_obj_set_pos(net_title, 12, 142);

    net_ssid_label_ = lv_label_create(screen_);
    lv_label_set_text(net_ssid_label_, "SSID: --");
    lv_obj_set_style_text_color(net_ssid_label_, COLOR_TEXT, 0);
    lv_obj_set_style_text_font(net_ssid_label_, &lv_font_montserrat_16, 0);
    lv_obj_set_pos(net_ssid_label_, 12, 168);

    net_host_label_ = lv_label_create(screen_);
    lv_label_set_text(net_host_label_, "Host: --");
    lv_obj_set_style_text_color(net_host_label_, COLOR_TEXT, 0);
    lv_obj_set_style_text_font(net_host_label_, &lv_font_montserrat_16, 0);
    lv_obj_set_pos(net_host_label_, 12, 192);

    lv_obj_t* hint = lv_label_create(screen_);
    lv_label_set_long_mode(hint, LV_LABEL_LONG_WRAP);
    lv_obj_set_width(hint, 296);
    lv_label_set_text(hint, "Configure via serial: AT+SSID / PASS / HOST / PORT");
    lv_obj_set_style_text_color(hint, COLOR_MUTED, 0);
    lv_obj_set_style_text_font(hint, &lv_font_montserrat_16, 0);
    lv_obj_set_pos(hint, 12, 216);

    ESP_LOGI(TAG, "Settings screen created");
}

void SettingsScreen::refresh() {
    // Don't read from NVS here — it can race with the uiTask's NVS write
    // and the handle isn't thread-safe. Use the cached volume_ value instead.
    // On first open, volume_ was set by the playback init at boot.
    updateVolumeLabel();

    // Network labels are read-only (no writes happen), safe to read.
    if (nvs_ && net_ssid_label_ && net_host_label_) {
        char buf[80] = {};

        if (nvs_->getWifiSSID(buf, sizeof(buf))) {
            lv_label_set_text_fmt(net_ssid_label_, "SSID: %s", buf);
        } else {
            lv_label_set_text(net_ssid_label_, "SSID: (default)");
        }

        if (nvs_->getBackendHost(buf, sizeof(buf))) {
            uint16_t port = nvs_->getBackendPort();
            lv_label_set_text_fmt(net_host_label_, "Host: %s:%d", buf, port);
        } else {
            lv_label_set_text(net_host_label_, "Host: (default)");
        }
    }
}

void SettingsScreen::updateVolumeLabel() {
    if (vol_label_) {
        char buf[8];
        snprintf(buf, sizeof(buf), "%d%%", volume_);
        lv_label_set_text(vol_label_, buf);
    }
}

// ─── Event callbacks ────────────────────────────────────────────────────────

void SettingsScreen::backCb(lv_event_t* e) {
    auto* self = static_cast<SettingsScreen*>(lv_event_get_user_data(e));
    // Volume is persisted from the uiTask (not here) to avoid flash writes
    // in the LVGL task context which crash the device.
    if (self->back_cb_) {
        self->back_cb_(self->back_ctx_);
    }
}

void SettingsScreen::volDownCb(lv_event_t* e) {
    auto* self = static_cast<SettingsScreen*>(lv_event_get_user_data(e));
    if (self->volume_ >= 10) {
        self->volume_ -= 10;
    } else {
        self->volume_ = 0;
    }
    self->updateVolumeLabel();
    if (self->playback_) {
        self->playback_->setVolume(self->volume_);
    }
}

void SettingsScreen::volUpCb(lv_event_t* e) {
    auto* self = static_cast<SettingsScreen*>(lv_event_get_user_data(e));
    if (self->volume_ <= 90) {
        self->volume_ += 10;
    } else {
        self->volume_ = 100;
    }
    self->updateVolumeLabel();
    if (self->playback_) {
        self->playback_->setVolume(self->volume_);
    }
}
