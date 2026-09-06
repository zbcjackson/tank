// Minimal esp_heap_caps.h shim for native tests — only what WsClient's opus
// path (codec state placement allocs) references. Implemented in
// esp_stubs.cpp.
#pragma once

#include <cstddef>
#include <cstdint>

#define MALLOC_CAP_SPIRAM   (1 << 10)
#define MALLOC_CAP_INTERNAL (1 << 11)

size_t heap_caps_get_free_size(int caps);
size_t heap_caps_get_largest_free_block(int caps);
void* heap_caps_malloc(size_t size, int caps);
void heap_caps_free(void* ptr);
