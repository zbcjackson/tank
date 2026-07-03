#pragma once

// Minimal ESP-IDF logging shim for native tests.
// Maps ESP_LOGx macros to printf (or no-op via NATIVE_TEST_SILENT_LOG).

#include <cstdio>

#ifdef NATIVE_TEST_SILENT_LOG
#define ESP_LOGE(tag, fmt, ...)
#define ESP_LOGW(tag, fmt, ...)
#define ESP_LOGI(tag, fmt, ...)
#define ESP_LOGD(tag, fmt, ...)
#define ESP_LOGV(tag, fmt, ...)
#else
#define ESP_LOGE(tag, fmt, ...) printf("E [%s] " fmt "\n", tag, ##__VA_ARGS__)
#define ESP_LOGW(tag, fmt, ...) printf("W [%s] " fmt "\n", tag, ##__VA_ARGS__)
#define ESP_LOGI(tag, fmt, ...) printf("I [%s] " fmt "\n", tag, ##__VA_ARGS__)
#define ESP_LOGD(tag, fmt, ...)
#define ESP_LOGV(tag, fmt, ...)
#endif
