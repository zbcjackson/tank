// Minimal FreeRTOS task/delay stubs for native tests.

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "freertos/stream_buffer.h"

BaseType_t xTaskCreatePinnedToCore(
    TaskFunction_t /*pvTaskCode*/,
    const char* /*pcName*/,
    uint32_t /*usStackDepth*/,
    void* /*pvParameters*/,
    UBaseType_t /*uxPriority*/,
    TaskHandle_t* pxCreatedTask,
    int /*xCoreID*/)
{
    if (pxCreatedTask) *pxCreatedTask = nullptr;
    return pdPASS;
}

void vTaskDelay(TickType_t /*xTicksToDelay*/) {
    // No-op in tests
}

void vTaskDelete(TaskHandle_t /*xTaskToDelete*/) {
    // No-op in tests
}

QueueHandle_t xQueueCreate(UBaseType_t /*uxQueueLength*/, UBaseType_t /*uxItemSize*/) {
    return (QueueHandle_t)1;  // Non-null sentinel
}

BaseType_t xQueueSend(QueueHandle_t /*xQueue*/, const void* /*pvItemToQueue*/, TickType_t /*xTicksToWait*/) {
    return pdPASS;
}

BaseType_t xQueueReceive(QueueHandle_t /*xQueue*/, void* /*pvBuffer*/, TickType_t /*xTicksToWait*/) {
    return pdFALSE;  // Nothing to receive by default
}

void vQueueDelete(QueueHandle_t /*xQueue*/) {
}

StreamBufferHandle_t xStreamBufferCreate(size_t /*xBufferSizeBytes*/, size_t /*xTriggerLevelBytes*/) {
    return (StreamBufferHandle_t)1;
}

size_t xStreamBufferSend(StreamBufferHandle_t /*xStreamBuffer*/, const void* /*pvTxData*/, size_t xDataLengthBytes, TickType_t /*xTicksToWait*/) {
    return xDataLengthBytes;
}

size_t xStreamBufferReceive(StreamBufferHandle_t /*xStreamBuffer*/, void* /*pvRxData*/, size_t /*xBufferLengthBytes*/, TickType_t /*xTicksToWait*/) {
    return 0;
}

BaseType_t xStreamBufferReset(StreamBufferHandle_t /*xStreamBuffer*/) {
    return pdPASS;
}

void vStreamBufferDelete(StreamBufferHandle_t /*xStreamBuffer*/) {
}
