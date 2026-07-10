#include "Cores3Display.h"
#include "screens/MainScreen.h"
#include "screens/SettingsScreen.h"
#include "settings/NvsSettings.h"
#include "app/Session.h"
#include "hal/cores3/Cores3Pins.h"
#include "config.h"

#include "driver/spi_master.h"
#include "driver/i2c.h"
#include "driver/gpio.h"
#include "esp_log.h"
#include "esp_lcd_panel_io.h"
#include "esp_lcd_panel_vendor.h"
#include "esp_lcd_panel_ops.h"
#include "esp_lvgl_port.h"
#include "esp_timer.h"
#include <cstring>

static const char* TAG = "Cores3Display";

// Static instance pointer so the static touch callback can reach the screens.
static Cores3Display* s_self = nullptr;

// Timer callback: wake the esp_lvgl_port task so it polls our custom indev.
// Without this, the port task only reads indevs on LVGL_PORT_EVENT_TOUCH which
// is only set by esp_lcd_touch drivers — our raw I2C indev would never be read.
static void touch_poll_timer_cb(void* arg) {
    (void)arg;
    lvgl_port_task_wake(LVGL_PORT_EVENT_TOUCH, nullptr);
}

// LVGL timer callback: polls the coordinate-based settings-gear flag and loads
// the settings screen. Runs inside lv_timer_handler (the LVGL task context) —
// the only safe place to call lv_scr_load. Calling lv_scr_load from the uiTask
// deadlocks LVGL; scheduling it via lv_async_call from the uiTask never flushes.
static void settings_poll_lv_timer_cb(lv_timer_t* t) {
    (void)t;
    if (s_self) s_self->pollSettingsFromLvglTask();
}

bool Cores3Display::init() {
    s_self = this;
    if (!initLCD()) return false;
    if (!initTouch()) return false;
    if (!initLVGL()) return false;

    // Create screens
    main_screen_ = new MainScreen();
    settings_screen_ = new SettingsScreen();

    // Lock LVGL before creating UI objects
    lvgl_port_lock(0);

    // Create main screen
    lv_obj_t* main_scr = lv_obj_create(nullptr);
    main_screen_->create(main_scr);

    // Create settings screen (not loaded yet)
    lv_obj_t* settings_scr = lv_obj_create(nullptr);
    settings_screen_->create(settings_scr);

    // Set initial volume from NVS (can't read NVS from LVGL task later, so do it now).
    if (nvs_) {
        uint8_t vol = nvs_->getVolume();
        settings_screen_->setInitialVolume(vol);
    }

    // Wire navigation callback (back button on settings screen still uses LVGL
    // events since it's the only button on that screen and works reliably alone).
    // The gear on the main screen uses coordinate-based detection: the touch
    // callback sets a flag, and settings_poll_lv_timer_cb (below) loads the
    // screen from the LVGL task context — the only place lv_scr_load is safe.
    settings_screen_->onBack([](void* ctx) {
        auto* self = static_cast<Cores3Display*>(ctx);
        self->showMain();
    }, this);

    // LVGL timer to poll the gear-tap flag from the LVGL task context (10ms).
    lv_timer_create(settings_poll_lv_timer_cb, 10, nullptr);

    // Load main screen
    lv_scr_load(main_scr);

    lvgl_port_unlock();

    showStatus("Initializing...");
    ESP_LOGI(TAG, "LVGL display initialized");
    return true;
}

bool Cores3Display::initLCD() {
    ESP_LOGI(TAG, "Initializing ILI9342C LCD (320x240)");

    // SPI bus for LCD
    spi_bus_config_t bus_cfg = {};
    bus_cfg.mosi_io_num = 37;
    bus_cfg.miso_io_num = -1;
    bus_cfg.sclk_io_num = 36;
    bus_cfg.quadwp_io_num = -1;
    bus_cfg.quadhd_io_num = -1;
    bus_cfg.max_transfer_sz = SCREEN_W * 10 * 2;  // 10 lines for partial rendering

    esp_err_t err = spi_bus_initialize(SPI2_HOST, &bus_cfg, SPI_DMA_CH_AUTO);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "SPI bus init failed: %s", esp_err_to_name(err));
        return false;
    }

    // Panel IO
    esp_lcd_panel_io_spi_config_t io_config = {};
    io_config.dc_gpio_num = CORES3_LCD_DC_PIN;
    io_config.cs_gpio_num = CORES3_LCD_CS_PIN;
    io_config.pclk_hz = 40 * 1000 * 1000;
    io_config.lcd_cmd_bits = 8;
    io_config.lcd_param_bits = 8;
    io_config.spi_mode = 0;
    // Espressif's SPI LCD note recommends a shallow queue (2-4) — fewer queued
    // transactions means fewer temp-buffer copies during a full-screen refresh.
    io_config.trans_queue_depth = 4;

    err = esp_lcd_new_panel_io_spi((esp_lcd_spi_bus_handle_t)SPI2_HOST, &io_config, &io_handle_);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "LCD panel IO init failed: %s", esp_err_to_name(err));
        return false;
    }

    // Panel driver (ILI9342C is ST7789-compatible)
    esp_lcd_panel_dev_config_t panel_config = {};
    panel_config.reset_gpio_num = CORES3_LCD_RST_PIN;
    panel_config.rgb_ele_order = LCD_RGB_ELEMENT_ORDER_BGR;
    panel_config.bits_per_pixel = 16;

    err = esp_lcd_new_panel_st7789(io_handle_, &panel_config, &panel_handle_);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "LCD panel init failed: %s", esp_err_to_name(err));
        return false;
    }

    esp_lcd_panel_reset(panel_handle_);
    esp_lcd_panel_init(panel_handle_);
    esp_lcd_panel_disp_on_off(panel_handle_, true);

    ESP_LOGI(TAG, "LCD initialized");
    return true;
}

bool Cores3Display::initTouch() {
    ESP_LOGI(TAG, "Initializing FT6336U touch at 0x%02X", CORES3_TOUCH_ADDR);

    // Device mode = normal (reg 0x00 = 0x00)
    uint8_t dev_mode[] = {0x00, 0x00};
    i2c_master_write_to_device(I2C_NUM_0, CORES3_TOUCH_ADDR, dev_mode, 2, pdMS_TO_TICKS(100));

    // INT mode = polling (reg 0xA4 = 0x00)
    uint8_t int_mode[] = {0xA4, 0x00};
    i2c_master_write_to_device(I2C_NUM_0, CORES3_TOUCH_ADDR, int_mode, 2, pdMS_TO_TICKS(100));

    // Verify presence via vendor ID (reg 0xA8)
    uint8_t reg = 0xA8;
    uint8_t vendor = 0;
    esp_err_t err = i2c_master_write_read_device(
        I2C_NUM_0, CORES3_TOUCH_ADDR, &reg, 1, &vendor, 1, pdMS_TO_TICKS(100));
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "FT6336U not responding: %s", esp_err_to_name(err));
    } else {
        ESP_LOGI(TAG, "FT6336U vendor ID = 0x%02X", vendor);
    }
    return true;
}

bool Cores3Display::initLVGL() {
    ESP_LOGI(TAG, "Initializing LVGL via esp_lvgl_port");

    // Initialize LVGL port (creates the LVGL task).
    // Allocate a generous 32KB stack from PSRAM: lv_scr_load(), lv_label word-
    // wrapping on long responses, and refresh() all need deep stack. The 7KB
    // default stack overflows on screen-switch; 16KB overflows on long text.
    lvgl_port_cfg_t lvgl_cfg = ESP_LVGL_PORT_INIT_CONFIG();
    lvgl_cfg.task_stack = 49152;  // 48KB from PSRAM — generous for deep call chains
    lvgl_cfg.task_stack_caps = MALLOC_CAP_SPIRAM | MALLOC_CAP_DEFAULT;
    esp_err_t err = lvgl_port_init(&lvgl_cfg);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "LVGL port init failed: %s", esp_err_to_name(err));
        return false;
    }

    // Add display.
    // Draw buffers MUST live in internal DMA-capable RAM, not PSRAM: the
    // ESP32-S3 SPI master cannot DMA directly from PSRAM, so with a PSRAM buffer
    // the driver falls back to allocating a temp internal-SRAM buffer and copying
    // per transaction. On a full-screen redraw (screen swap) that fallback fails
    // under memory pressure — "spi transmit (queue) color failed" — and the LVGL
    // flush never completes, freezing the UI. buff_dma=true + buff_spiram=false
    // places the buffers in internal DMA RAM and removes the fallback entirely.
    // 10 lines × 320 × 2 bytes × 2 buffers ≈ 12.8KB internal RAM. Kept small so
    // internal DMA RAM stays available for the WebSocket task and other tasks
    // (a larger buffer starves xTaskCreate for the websocket client → ESP_FAIL).
    const lvgl_port_display_cfg_t disp_cfg = {
        .io_handle = io_handle_,
        .panel_handle = panel_handle_,
        .buffer_size = SCREEN_W * 10,  // 10 lines partial rendering (internal RAM)
        .double_buffer = true,
        .hres = SCREEN_W,
        .vres = SCREEN_H,
        .monochrome = false,
        .rotation = {
            .swap_xy = false,
            .mirror_x = false,
            .mirror_y = false,
        },
        .flags = {
            .buff_dma = true,
            .buff_spiram = false,
            .sw_rotate = false,
            .swap_bytes = true,
            .full_refresh = false,
            .direct_mode = false,
        },
    };

    lv_display_ = lvgl_port_add_disp(&disp_cfg);
    if (!lv_display_) {
        ESP_LOGE(TAG, "Failed to add LVGL display");
        return false;
    }

    // Add touch input device (custom read callback).
    // Use LV_INDEV_MODE_EVENT — the esp_lvgl_port task calls lv_indev_read()
    // directly when LVGL_PORT_EVENT_TOUCH is received. We fire that event from
    // a periodic timer (20ms) to ensure the indev is polled regularly.
    // In event mode, lv_timer_handler() does NOT read the indev on its own,
    // avoiding the double-read that breaks the press→release state machine.
    lvgl_port_lock(0);
    lv_touch_ = lv_indev_create();
    lv_indev_set_type(lv_touch_, LV_INDEV_TYPE_POINTER);
    lv_indev_set_read_cb(lv_touch_, touchReadCb);
    lv_indev_set_display(lv_touch_, lv_display_);
    lv_indev_set_mode(lv_touch_, LV_INDEV_MODE_EVENT);
    lvgl_port_unlock();

    // Periodic timer to wake the esp_lvgl_port task so it calls lv_indev_read().
    esp_timer_handle_t touch_timer = nullptr;
    esp_timer_create_args_t timer_args = {};
    timer_args.callback = touch_poll_timer_cb;
    timer_args.name = "touch_poll";
    esp_timer_create(&timer_args, &touch_timer);
    esp_timer_start_periodic(touch_timer, 20 * 1000);  // 20ms

    ESP_LOGI(TAG, "LVGL initialized (display + touch)");
    return true;
}

// ─── Touch read callback for LVGL ──────────────────────────────────────────

void Cores3Display::touchReadCb(lv_indev_t* indev, lv_indev_data_t* data) {
    (void)indev;

    // Read FT6336U touch data via I2C
    uint8_t touch_data[7] = {};
    uint8_t reg = 0x02;

    esp_err_t err = i2c_master_write_read_device(
        I2C_NUM_0, CORES3_TOUCH_ADDR,
        &reg, 1, touch_data, sizeof(touch_data),
        pdMS_TO_TICKS(10)
    );

    if (err != ESP_OK) {
        // I2C read failed (bus contention with audio codec). Treat as "no
        // touch" so PTT can't get stuck ON — a stuck PTT streams audio forever.
        if (s_self && s_self->main_screen_) {
            s_self->main_screen_->updatePTTFromTouch(false, 0, 0);
            s_self->main_screen_->updateHeaderButtonsFromTouch(false, 0, 0);
        }
        data->state = LV_INDEV_STATE_RELEASED;
        return;
    }

    uint8_t touch_count = touch_data[0] & 0x0F;
    if (touch_count > 0) {
        uint16_t x = ((touch_data[1] & 0x0F) << 8) | touch_data[2];
        uint16_t y = ((touch_data[3] & 0x0F) << 8) | touch_data[4];

        // This callback runs during LVGL's input-read phase. It must ONLY report
        // input state and set lightweight flags — never mutate the widget tree
        // or load screens here (that corrupts LVGL state and freezes the UI).
        // Header taps set flags consumed by the uiTask (see handleTouchRequests).
        if (s_self && s_self->main_screen_) {
            s_self->main_screen_->updatePTTFromTouch(true, x, y);
            s_self->main_screen_->updateHeaderButtonsFromTouch(true, x, y);
        }

        data->point.x = x;
        data->point.y = y;
        data->state = LV_INDEV_STATE_PRESSED;
    } else {
        // No touch — clear PTT immediately (level-based = can't get stuck).
        if (s_self && s_self->main_screen_) {
            s_self->main_screen_->updatePTTFromTouch(false, 0, 0);
            s_self->main_screen_->updateHeaderButtonsFromTouch(false, 0, 0);
        }

        data->state = LV_INDEV_STATE_RELEASED;
    }
}

// ─── Display interface implementation ───────────────────────────────────────

// Helper: try to lock LVGL with a short timeout. If the LVGL port task is busy
// rendering or processing touch, we skip this update rather than block the
// uiTask (which would starve touch polling and cause the "stuck" feel).
// The uiTask loops every 20ms, so skipped updates are retried immediately.
static inline bool tryLock() { return lvgl_port_lock(10); }

void Cores3Display::showStatus(const char* status) {
    if (!tryLock()) return;
    if (main_screen_) main_screen_->setStatus(status);
    lvgl_port_unlock();
}

void Cores3Display::showUserText(const char* text) {
    // Transcribed text is not rendered on screen; the activity indicator
    // reflects state instead. Kept for the Display interface / logging.
    (void)text;
}

void Cores3Display::showAssistantText(const char* text) {
    // Reply text is not rendered on screen; show the speaking state instead.
    (void)text;
    if (!tryLock()) return;
    if (main_screen_) {
        main_screen_->setActivityState((int)Session::State::SPEAKING);
    }
    lvgl_port_unlock();
}

void Cores3Display::showThinking(bool active) {
    if (!tryLock()) return;
    if (main_screen_) main_screen_->setThinking(active);
    lvgl_port_unlock();
}

void Cores3Display::showError(const char* error) {
    if (!tryLock()) return;
    if (main_screen_) main_screen_->setError(error);
    lvgl_port_unlock();
}

void Cores3Display::clear() {
    // LVGL manages rendering — nothing to do
}

bool Cores3Display::pollPressed() {
    // Driven by LVGL button events on the PTT button.
    // No lock needed — reads a volatile bool.
    if (main_screen_) {
        return main_screen_->isPTTPressed();
    }
    return false;
}

bool Cores3Display::consumeNewConversationRequest() {
    // Set by the new-conversation button's LVGL CLICKED callback; polled by the
    // ws_send task. No lock needed — poll-and-clear of a volatile bool.
    if (main_screen_) {
        return main_screen_->consumeNewConvRequest();
    }
    return false;
}

void Cores3Display::showTalkState(bool listening) {
    // Use a longer lock timeout (200ms) than other UI updates — the PTT
    // highlight is important and infrequent, so it must not be dropped when
    // the LVGL task is busy rendering a response (which would leave the button
    // stuck green after release).
    if (!lvgl_port_lock(200)) return;
    if (main_screen_) main_screen_->setPTTState(listening);
    lvgl_port_unlock();
}

void Cores3Display::setActivityState(int state) {
    if (!tryLock()) return;
    if (main_screen_) main_screen_->setActivityState(state);
    lvgl_port_unlock();
}

// Async screen-load trampolines. lv_scr_load() must NOT be called from inside
// a button event callback — LVGL is mid-iteration over the current screen's
// objects and swapping the screen out corrupts its state (freeze). lv_async_call
// defers the load to the start of the next lv_timer_handler cycle, after event
// processing has finished.
static void loadSettingsAsync(void* arg) {
    auto* self = static_cast<Cores3Display*>(arg);
    self->loadSettingsScreen();
}

static void loadMainAsync(void* arg) {
    auto* self = static_cast<Cores3Display*>(arg);
    self->loadMainScreen();
}

void Cores3Display::loadSettingsScreen() {
    if (settings_screen_) {
        settings_screen_->setHAL(hal_);
        settings_screen_->setNvsSettings(nvs_);
        settings_screen_->setPlayback(playback_);
        settings_screen_->refresh();
        lv_scr_load(settings_screen_->getScreen());
    }
}

void Cores3Display::loadMainScreen() {
    if (main_screen_) {
        // Mark volume dirty so the uiTask persists it to NVS from its own context.
        volume_dirty_ = true;
        lv_scr_load(main_screen_->getScreen());
    }
}

uint8_t Cores3Display::getSettingsVolume() const {
    if (settings_screen_) {
        return settings_screen_->getVolume();
    }
    return 70;
}

void Cores3Display::pollSettingsFromLvglTask() {
    // Runs from settings_poll_lv_timer_cb, i.e. inside lv_timer_handler in the
    // LVGL task. Mirrors the back button's approach: schedule via lv_async_call
    // so the actual lv_scr_load runs at the START of the next lv_timer_handler
    // cycle (before timer iteration), not mid-iteration (which freezes).
    // lv_async_call scheduled from the LVGL task flushes reliably — unlike from
    // the uiTask, which never flushes in this LV_INDEV_MODE_EVENT setup.
    if (main_screen_ && main_screen_->consumeSettingsRequest()) {
        lv_async_call(loadSettingsAsync, this);
    }
}

void Cores3Display::showMain() {
    lv_async_call(loadMainAsync, this);
}
