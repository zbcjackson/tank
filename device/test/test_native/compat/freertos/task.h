#pragma once

#include "FreeRTOS.h"

typedef void (*TaskFunction_t)(void*);

BaseType_t xTaskCreatePinnedToCore(
    TaskFunction_t pvTaskCode,
    const char* pcName,
    uint32_t usStackDepth,
    void* pvParameters,
    UBaseType_t uxPriority,
    TaskHandle_t* pxCreatedTask,
    int xCoreID
);

void vTaskDelay(TickType_t xTicksToDelay);
void vTaskDelete(TaskHandle_t xTaskToDelete);
