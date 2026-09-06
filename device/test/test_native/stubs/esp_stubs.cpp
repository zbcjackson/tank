// ESP-IDF stubs for native tests.
// Provides: esp_read_mac, esp_err_to_name, esp_restart.

#include "esp_err.h"
#include "esp_mac.h"
#include "esp_system.h"
#include "esp_stubs.h"

#include <cstring>
#include <cstdio>

static uint8_t fake_mac[6] = {0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF};

void esp_stubs_reset() {
    uint8_t default_mac[6] = {0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF};
    memcpy(fake_mac, default_mac, 6);
}

void esp_stubs_set_mac(const uint8_t mac[6]) {
    memcpy(fake_mac, mac, 6);
}

int esp_read_mac(uint8_t* mac, esp_mac_type_t /*type*/) {
    memcpy(mac, fake_mac, 6);
    return 0;  // ESP_OK
}

const char* esp_err_to_name(esp_err_t code) {
    switch (code) {
        case ESP_OK: return "ESP_OK";
        case ESP_FAIL: return "ESP_FAIL";
        default: return "UNKNOWN_ERROR";
    }
}

void esp_restart() {
    // No-op in tests — factoryReset() calls this but we don't want to exit.
}

// heap_caps stubs — WsClient's opus path (codec state placement allocs)
// would otherwise not link. Returns real malloc'd memory so behaviour holds.
#include "esp_heap_caps.h"
#include <cstdlib>
size_t heap_caps_get_free_size(int /*caps*/) { return 32 * 1024 * 1024; }
size_t heap_caps_get_largest_free_block(int /*caps*/) { return 8 * 1024 * 1024; }
void* heap_caps_malloc(size_t size, int /*caps*/) { return malloc(size); }
void heap_caps_free(void* ptr) { free(ptr); }
int64_t esp_timer_get_time() { return 0; }
