// LVGL's builtin allocator pool, placed in PSRAM (P1-2 Step 5 memory budget).
//
// LVGL v9's lv_mem_core_builtin.c consults LV_MEM_POOL_ALLOC(size) when
// defined: the 64 KB tlsf pool comes from this call instead of a static
// internal-RAM array — the single largest internal-RAM consumer on this
// firmware. UI object metadata tolerates PSRAM latency (draw buffers stay
// in internal DMA RAM); LVGL never de-inits, so the pool is intentionally
// not freed.
#pragma once

#include "esp_heap_caps.h"

#ifndef LV_MEM_POOL_ALLOC
#define LV_MEM_POOL_ALLOC(size) heap_caps_malloc((size), MALLOC_CAP_SPIRAM)
#endif
