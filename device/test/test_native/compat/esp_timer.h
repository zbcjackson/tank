// Minimal esp_timer.h shim for native tests.
#pragma once

#include <cstdint>

int64_t esp_timer_get_time();
