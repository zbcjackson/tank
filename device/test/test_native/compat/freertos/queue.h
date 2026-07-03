#pragma once

#include "FreeRTOS.h"

// Minimal queue API declarations (stubs in freertos_stubs.cpp if needed)
QueueHandle_t xQueueCreate(UBaseType_t uxQueueLength, UBaseType_t uxItemSize);
BaseType_t xQueueSend(QueueHandle_t xQueue, const void* pvItemToQueue, TickType_t xTicksToWait);
BaseType_t xQueueReceive(QueueHandle_t xQueue, void* pvBuffer, TickType_t xTicksToWait);
void vQueueDelete(QueueHandle_t xQueue);
