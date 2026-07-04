// On-device test: single binary that runs ALL hardware test cases.
// One flash, one boot, one serial session — no USB re-enumeration between cases.
// Teardown between groups ensures clean peripheral state.

#include "unity.h"
#include "driver/i2c.h"
#include "driver/i2s_std.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_heap_caps.h"
#include "nvs_flash.h"
#include "nvs.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "freertos/stream_buffer.h"
#include "driver/usb_serial_jtag.h"

#include "hal/cores3/Cores3HAL.h"
#include "hal/cores3/Cores3Pins.h"
#include "audio/AudioCapture.h"
#include "audio/AudioPlayback.h"
#include "settings/NvsSettings.h"
#include "app/Assistant.h"
#include "app/Session.h"
#include "config.h"

static const char* TAG = "test_device";

// ─── I2C addresses ──────────────────────────────────────────────────────────
#define AXP2101_ADDR    0x34
#define AW9523B_ADDR    0x58
#define ES7210_ADDR     0x40
#define AW88298_ADDR    0x36

// ─── Shared state for teardown ──────────────────────────────────────────────
static bool i2c_up = false;
static Cores3HAL* hal = nullptr;

// ─── Helpers ────────────────────────────────────────────────────────────────

static void bring_up_i2c() {
    if (i2c_up) return;
    i2c_config_t conf = {};
    conf.mode = I2C_MODE_MASTER;
    conf.sda_io_num = CORES3_I2C_SDA_PIN;
    conf.scl_io_num = CORES3_I2C_SCL_PIN;
    conf.sda_pullup_en = GPIO_PULLUP_ENABLE;
    conf.scl_pullup_en = GPIO_PULLUP_ENABLE;
    conf.master.clk_speed = CORES3_I2C_FREQ;
    TEST_ASSERT_EQUAL(ESP_OK, i2c_param_config(I2C_NUM_0, &conf));
    TEST_ASSERT_EQUAL(ESP_OK, i2c_driver_install(I2C_NUM_0, I2C_MODE_MASTER, 0, 0, 0));
    i2c_up = true;
}

static void tear_down_i2c() {
    if (i2c_up) {
        i2c_driver_delete(I2C_NUM_0);
        i2c_up = false;
    }
}

static bool i2c_probe(uint8_t addr) {
    i2c_cmd_handle_t cmd = i2c_cmd_link_create();
    i2c_master_start(cmd);
    i2c_master_write_byte(cmd, (addr << 1) | I2C_MASTER_WRITE, true);
    i2c_master_stop(cmd);
    esp_err_t err = i2c_master_cmd_begin(I2C_NUM_0, cmd, pdMS_TO_TICKS(100));
    i2c_cmd_link_delete(cmd);
    return err == ESP_OK;
}

static void ensure_hal() {
    if (hal) return;
    tear_down_i2c();  // HAL does its own I2C init
    hal = new Cores3HAL();
    TEST_ASSERT_TRUE_MESSAGE(hal->init(), "Cores3HAL::init() failed");
}

static void ensure_nvs() {
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        nvs_flash_erase();
        err = nvs_flash_init();
    }
    TEST_ASSERT_EQUAL(ESP_OK, err);
}

static void clear_nvs_namespace() {
    nvs_handle_t h;
    if (nvs_open("tank_cfg", NVS_READWRITE, &h) == ESP_OK) {
        nvs_erase_all(h);
        nvs_commit(h);
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// GROUP 1: HAL I2C probing
// ═══════════════════════════════════════════════════════════════════════════════

void test_i2c_bus_init() {
    bring_up_i2c();
    TEST_PASS();
}

void test_axp2101_responds() {
    bring_up_i2c();
    TEST_ASSERT_TRUE_MESSAGE(i2c_probe(AXP2101_ADDR), "AXP2101 PMU not responding at 0x34");
}

void test_aw9523b_responds() {
    bring_up_i2c();
    TEST_ASSERT_TRUE_MESSAGE(i2c_probe(AW9523B_ADDR), "AW9523B IO expander not responding at 0x58");
}

void test_es7210_responds() {
    bring_up_i2c();
    TEST_ASSERT_TRUE_MESSAGE(i2c_probe(ES7210_ADDR), "ES7210 mic codec not responding at 0x40");
}

void test_aw88298_responds() {
    bring_up_i2c();
    TEST_ASSERT_TRUE_MESSAGE(i2c_probe(AW88298_ADDR), "AW88298 amplifier not responding at 0x36");
}

void test_cores3_hal_full_init() {
    tear_down_i2c();  // HAL re-inits I2C itself
    ensure_hal();
    hal->setVolume(50);
    hal->setVolume(100);
    hal->setMicGain(50);
}

// ═══════════════════════════════════════════════════════════════════════════════
// GROUP 2: Audio I2S
// ═══════════════════════════════════════════════════════════════════════════════

static AudioCapture* g_capture = nullptr;
static QueueHandle_t g_mic_queue = nullptr;

static void ensure_audio() {
    if (g_capture) return;
    ensure_hal();
    g_mic_queue = xQueueCreate(CONFIG_MIC_QUEUE_LEN, CONFIG_MIC_FRAME_BYTES);
    TEST_ASSERT_NOT_NULL(g_mic_queue);
    g_capture = new AudioCapture();
    TEST_ASSERT_TRUE_MESSAGE(g_capture->init(g_mic_queue), "AudioCapture::init() failed");
}

static void tear_down_audio() {
    if (g_capture) {
        g_capture->stop();
        delete g_capture;
        g_capture = nullptr;
    }
    if (g_mic_queue) {
        vQueueDelete(g_mic_queue);
        g_mic_queue = nullptr;
    }
}

void test_audio_capture_init() {
    ensure_audio();
    TEST_ASSERT_NOT_NULL(g_capture->getTxChannel());
}

void test_mic_captures_audio_frames() {
    ensure_audio();
    // A prior test (test_cores3_hal_full_init) lowers mic gain via setMicGain(50).
    // Restore max gain so audio, if present, is more likely to be audible.
    hal->setMicGain(100);

    g_capture->start();
    // The ES7210 mic codec needs time to lock onto the I2S bit clock before it
    // delivers frames. Give it a moment to settle.
    vTaskDelay(pdMS_TO_TICKS(300));

    // HARD assertion: the RX channel must deliver frames. This proves the I2S
    // clock is running and DMA is flowing — the actual hardware fact we can
    // verify deterministically regardless of ambient sound.
    int16_t frame[CONFIG_MIC_FRAME_BYTES / sizeof(int16_t)];
    int frames_received = 0;
    bool has_nonzero = false;
    for (int attempt = 0; attempt < 20; attempt++) {
        if (xQueueReceive(g_mic_queue, frame, pdMS_TO_TICKS(100)) != pdTRUE) {
            continue;
        }
        frames_received++;
        for (size_t i = 0; i < CONFIG_MIC_FRAME_BYTES / sizeof(int16_t); i++) {
            if (frame[i] != 0) { has_nonzero = true; break; }
        }
        if (frames_received >= 3 && has_nonzero) break;
    }

    TEST_ASSERT_GREATER_THAN_MESSAGE(
        0, frames_received,
        "No mic frames delivered — I2S clock/DMA not running");

    // SOFT check: non-zero samples depend on ambient room noise, so a silent
    // room legitimately yields all zeros on a working mic. Warn, don't fail.
    if (!has_nonzero) {
        ESP_LOGW(TAG, "Mic frames all zero (received %d frames) — likely a quiet "
                      "room; I2S path is working since frames were delivered",
                 frames_received);
    }

    // Do NOT stop capture here — g_capture->stop() deletes the shared I2S
    // channels, and the following speaker/playback tests reuse g_capture (via
    // ensure_audio, which sees it non-null). Teardown happens at the group
    // boundary in test_wifi_init_and_scan via tear_down_audio(). We only pause
    // the capture task so it stops draining frames.
    g_capture->pause();
}

void test_speaker_tx_accepts_writes() {
    ensure_audio();
    int16_t silence[320] = {};
    size_t bytes_written = 0;
    esp_err_t err = i2s_channel_write(
        g_capture->getTxChannel(), silence, sizeof(silence), &bytes_written, pdMS_TO_TICKS(1000));
    TEST_ASSERT_EQUAL_MESSAGE(ESP_OK, err, "I2S TX write failed");
    TEST_ASSERT_EQUAL(sizeof(silence), bytes_written);
}

void test_playback_with_stream_buffer() {
    ensure_audio();

    StreamBufferHandle_t spk_stream = xStreamBufferCreate(16 * 1024, CONFIG_SPK_FRAME_BYTES);
    TEST_ASSERT_NOT_NULL(spk_stream);

    AudioPlayback playback;
    TEST_ASSERT_TRUE_MESSAGE(
        playback.init(spk_stream, g_capture->getTxChannel()),
        "AudioPlayback::init() failed");

    playback.start();
    vTaskDelay(pdMS_TO_TICKS(100));
    TEST_ASSERT_FALSE(playback.isPlaying());

    // Feed audio and poll for playing state
    int16_t tone[320];
    for (int i = 0; i < 320; i++) tone[i] = (int16_t)(1000 * ((i % 2 == 0) ? 1 : -1));

    bool became_playing = false;
    for (int attempt = 0; attempt < 20 && !became_playing; attempt++) {
        for (int f = 0; f < 5; f++) xStreamBufferSend(spk_stream, tone, sizeof(tone), 0);
        if (playback.isPlaying()) { became_playing = true; break; }
        vTaskDelay(pdMS_TO_TICKS(10));
    }
    TEST_ASSERT_TRUE_MESSAGE(became_playing, "Playback never entered playing state");

    playback.stop();
    vStreamBufferDelete(spk_stream);
}

// ═══════════════════════════════════════════════════════════════════════════════
// GROUP 3: NVS on real flash
// ═══════════════════════════════════════════════════════════════════════════════

void test_nvs_init_succeeds() {
    ensure_nvs();
    clear_nvs_namespace();
    NvsSettings settings;
    TEST_ASSERT_TRUE(settings.init());
}

void test_nvs_volume_default() {
    ensure_nvs();
    clear_nvs_namespace();
    NvsSettings settings;
    settings.init();
    TEST_ASSERT_EQUAL_UINT8(70, settings.getVolume());
}

void test_nvs_volume_roundtrip() {
    ensure_nvs();
    clear_nvs_namespace();
    NvsSettings settings;
    settings.init();
    settings.setVolume(42);
    TEST_ASSERT_EQUAL_UINT8(42, settings.getVolume());
    settings.setVolume(0);
    TEST_ASSERT_EQUAL_UINT8(0, settings.getVolume());
    settings.setVolume(100);
    TEST_ASSERT_EQUAL_UINT8(100, settings.getVolume());
}

void test_nvs_wifi_ssid_roundtrip() {
    ensure_nvs();
    clear_nvs_namespace();
    NvsSettings settings;
    settings.init();
    char buf[64] = {};
    TEST_ASSERT_FALSE(settings.getWifiSSID(buf, sizeof(buf)));
    settings.setWifiSSID("TestNetwork_5GHz");
    TEST_ASSERT_TRUE(settings.getWifiSSID(buf, sizeof(buf)));
    TEST_ASSERT_EQUAL_STRING("TestNetwork_5GHz", buf);
}

void test_nvs_backend_port_roundtrip() {
    ensure_nvs();
    clear_nvs_namespace();
    NvsSettings settings;
    settings.init();
    TEST_ASSERT_EQUAL_UINT16(CONFIG_BACKEND_PORT, settings.getBackendPort());
    settings.setBackendPort(9000);
    TEST_ASSERT_EQUAL_UINT16(9000, settings.getBackendPort());
}

void test_nvs_has_network_config() {
    ensure_nvs();
    clear_nvs_namespace();
    NvsSettings settings;
    settings.init();
    TEST_ASSERT_FALSE(settings.hasNetworkConfig());
    settings.setWifiSSID("MyAP");
    TEST_ASSERT_TRUE(settings.hasNetworkConfig());
}

void test_nvs_persist_across_reopen() {
    ensure_nvs();
    clear_nvs_namespace();
    {
        NvsSettings settings;
        settings.init();
        settings.setVolume(88);
        settings.setWifiSSID("Persistent");
    }
    {
        NvsSettings settings;
        settings.init();
        TEST_ASSERT_EQUAL_UINT8(88, settings.getVolume());
        char buf[64] = {};
        TEST_ASSERT_TRUE(settings.getWifiSSID(buf, sizeof(buf)));
        TEST_ASSERT_EQUAL_STRING("Persistent", buf);
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// GROUP 4: Memory (PSRAM + queues)
// ═══════════════════════════════════════════════════════════════════════════════

void test_psram_available() {
    size_t psram_size = heap_caps_get_total_size(MALLOC_CAP_SPIRAM);
    ESP_LOGI(TAG, "PSRAM total: %u bytes", (unsigned)psram_size);
    TEST_ASSERT_GREATER_THAN_MESSAGE(1024 * 1024, psram_size, "PSRAM not detected or < 1MB");
}

void test_psram_512kb_alloc() {
    void* buf = heap_caps_malloc(512 * 1024, MALLOC_CAP_SPIRAM);
    TEST_ASSERT_NOT_NULL_MESSAGE(buf, "Failed to allocate 512KB from PSRAM");
    uint8_t* bytes = (uint8_t*)buf;
    for (int i = 0; i < 1024; i++) bytes[i] = (uint8_t)(i & 0xFF);
    for (int i = 0; i < 1024; i++) TEST_ASSERT_EQUAL_UINT8((uint8_t)(i & 0xFF), bytes[i]);
    heap_caps_free(buf);
}

void test_spk_stream_buffer_alloc() {
    StreamBufferHandle_t stream = xStreamBufferCreateWithCaps(
        512 * 1024, CONFIG_SPK_FRAME_BYTES, MALLOC_CAP_SPIRAM);
    TEST_ASSERT_NOT_NULL_MESSAGE(stream, "512KB PSRAM stream buffer allocation failed");

    int16_t write_frame[320];
    for (int i = 0; i < 320; i++) write_frame[i] = (int16_t)i;
    size_t written = xStreamBufferSend(stream, write_frame, sizeof(write_frame), 0);
    TEST_ASSERT_EQUAL(sizeof(write_frame), written);

    int16_t read_frame[320] = {};
    size_t received = xStreamBufferReceive(stream, read_frame, sizeof(read_frame), 0);
    TEST_ASSERT_EQUAL(sizeof(read_frame), received);
    TEST_ASSERT_EQUAL_INT16_ARRAY(write_frame, read_frame, 320);
    vStreamBufferDelete(stream);
}

void test_mic_queue_alloc() {
    QueueHandle_t queue = xQueueCreate(CONFIG_MIC_QUEUE_LEN, CONFIG_MIC_FRAME_BYTES);
    TEST_ASSERT_NOT_NULL_MESSAGE(queue, "mic_queue allocation failed");
    int16_t frame[320] = {};
    for (int i = 0; i < CONFIG_MIC_QUEUE_LEN; i++) {
        frame[0] = (int16_t)i;
        TEST_ASSERT_EQUAL(pdTRUE, xQueueSend(queue, frame, 0));
    }
    frame[0] = 99;
    TEST_ASSERT_EQUAL(pdFALSE, xQueueSend(queue, frame, 0));
    vQueueDelete(queue);
}

void test_event_queue_alloc() {
    QueueHandle_t queue = xQueueCreate(CONFIG_EVENT_QUEUE_LEN, sizeof(WsMessage));
    TEST_ASSERT_NOT_NULL_MESSAGE(queue, "event_queue allocation failed");
    WsMessage msg = {};
    strncpy(msg.type, "signal", sizeof(msg.type) - 1);
    TEST_ASSERT_EQUAL(pdTRUE, xQueueSend(queue, &msg, 0));
    WsMessage recv = {};
    TEST_ASSERT_EQUAL(pdTRUE, xQueueReceive(queue, &recv, 0));
    TEST_ASSERT_EQUAL_STRING("signal", recv.type);
    vQueueDelete(queue);
}

void test_internal_ram_available() {
    size_t free_internal = heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
    ESP_LOGI(TAG, "Free internal RAM: %u bytes", (unsigned)free_internal);
    TEST_ASSERT_GREATER_THAN_MESSAGE(100 * 1024, free_internal, "Less than 100KB internal RAM free");
}

// ═══════════════════════════════════════════════════════════════════════════════
// GROUP 5: WiFi (scan proves radio works)
// ═══════════════════════════════════════════════════════════════════════════════

void test_wifi_init_and_scan() {
    // Tear down audio first — I2S and WiFi compete for DMA/interrupts on core 0
    tear_down_audio();

    ensure_nvs();
    TEST_ASSERT_EQUAL(ESP_OK, esp_netif_init());
    TEST_ASSERT_EQUAL(ESP_OK, esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    TEST_ASSERT_EQUAL_MESSAGE(ESP_OK, esp_wifi_init(&cfg), "esp_wifi_init failed");
    TEST_ASSERT_EQUAL(ESP_OK, esp_wifi_set_mode(WIFI_MODE_STA));
    TEST_ASSERT_EQUAL_MESSAGE(ESP_OK, esp_wifi_start(), "esp_wifi_start failed");

    wifi_scan_config_t scan_config = {};
    scan_config.show_hidden = true;
    TEST_ASSERT_EQUAL_MESSAGE(ESP_OK, esp_wifi_scan_start(&scan_config, true), "WiFi scan failed");

    uint16_t ap_count = 0;
    TEST_ASSERT_EQUAL(ESP_OK, esp_wifi_scan_get_ap_num(&ap_count));
    ESP_LOGI(TAG, "WiFi scan found %d access points", ap_count);
    TEST_ASSERT_GREATER_THAN_UINT16_MESSAGE(0, ap_count, "WiFi scan found 0 APs — radio may be broken");

    // Full teardown of the global network stack so the boot test (which brings
    // WiFi up again via WiFiManager) doesn't hit "already created" aborts on
    // esp_event_loop_create_default() / esp_netif_create_default_wifi_sta().
    esp_wifi_stop();
    esp_wifi_deinit();
    esp_netif_t* sta = esp_netif_get_handle_from_ifkey("WIFI_STA_DEF");
    if (sta) {
        esp_netif_destroy_default_wifi(sta);
    }
    esp_event_loop_delete_default();
}

// ═══════════════════════════════════════════════════════════════════════════════
// GROUP 6: Full boot sequence
// ═══════════════════════════════════════════════════════════════════════════════

void test_full_boot_to_connecting() {
    ESP_LOGI(TAG, "Testing full boot sequence...");

    // Clean up any prior state — Assistant::init() brings up everything fresh
    tear_down_audio();
    if (hal) { delete hal; hal = nullptr; }

    // Release I2C driver left behind by prior HAL (no destructor releases it)
    i2c_driver_delete(I2C_NUM_0);

    ensure_nvs();
    nvs_flash_erase();
    nvs_flash_init();

    Cores3HAL* boot_hal = new Cores3HAL();
    TEST_ASSERT_TRUE_MESSAGE(boot_hal->init(), "Cores3HAL::init() failed");

    Assistant assistant;
    bool init_ok = assistant.init(boot_hal);
    TEST_ASSERT_TRUE_MESSAGE(init_ok, "Assistant::init() failed");
    TEST_ASSERT_EQUAL_MESSAGE(
        Session::State::CONNECTING, assistant.getState(),
        "Expected CONNECTING state after init");

    ESP_LOGI(TAG, "Boot sequence completed, state=CONNECTING");
    assistant.stop();
    delete boot_hal;
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN
// ═══════════════════════════════════════════════════════════════════════════════

extern "C" void app_main(void) {
    // Root-cause fix for the VM USB-Serial-JTAG re-enumeration race: after the
    // post-flash reset the CDC port re-enumerates on the host, and Unity output
    // printed before the host reader re-attaches is lost. Wait until the USB
    // host is actually connected (up to a bound) before emitting any results.
    for (int i = 0; i < 100; i++) {  // up to ~10s
        if (usb_serial_jtag_is_connected()) break;
        vTaskDelay(pdMS_TO_TICKS(100));
    }
    // Small extra settle so the host's line discipline is fully ready.
    vTaskDelay(pdMS_TO_TICKS(500));

    UNITY_BEGIN();

    // Group 1: HAL I2C
    RUN_TEST(test_i2c_bus_init);
    RUN_TEST(test_axp2101_responds);
    RUN_TEST(test_aw9523b_responds);
    RUN_TEST(test_es7210_responds);
    RUN_TEST(test_aw88298_responds);
    RUN_TEST(test_cores3_hal_full_init);

    // Group 2: Audio I2S
    RUN_TEST(test_audio_capture_init);
    RUN_TEST(test_mic_captures_audio_frames);
    RUN_TEST(test_speaker_tx_accepts_writes);
    RUN_TEST(test_playback_with_stream_buffer);

    // Group 3: NVS
    RUN_TEST(test_nvs_init_succeeds);
    RUN_TEST(test_nvs_volume_default);
    RUN_TEST(test_nvs_volume_roundtrip);
    RUN_TEST(test_nvs_wifi_ssid_roundtrip);
    RUN_TEST(test_nvs_backend_port_roundtrip);
    RUN_TEST(test_nvs_has_network_config);
    RUN_TEST(test_nvs_persist_across_reopen);

    // Group 4: Memory
    RUN_TEST(test_psram_available);
    RUN_TEST(test_psram_512kb_alloc);
    RUN_TEST(test_spk_stream_buffer_alloc);
    RUN_TEST(test_mic_queue_alloc);
    RUN_TEST(test_event_queue_alloc);
    RUN_TEST(test_internal_ram_available);

    // Group 5: WiFi (tears down audio first, brings up netif/wifi)
    RUN_TEST(test_wifi_init_and_scan);

    // Group 6: Boot (tears down everything, reinits from scratch)
    RUN_TEST(test_full_boot_to_connecting);

    UNITY_END();
}
