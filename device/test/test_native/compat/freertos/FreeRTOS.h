#pragma once

// Minimal FreeRTOS types for native compilation.

#include <cstdint>
#include <cstddef>

typedef uint32_t TickType_t;
typedef int BaseType_t;
typedef unsigned int UBaseType_t;

#define pdTRUE   1
#define pdFALSE  0
#define pdPASS   pdTRUE
#define pdMS_TO_TICKS(ms) ((TickType_t)(ms))

typedef void* TaskHandle_t;
typedef void* QueueHandle_t;
typedef void* StreamBufferHandle_t;
