#pragma once

// Minimal esp_event.h compat shim for native tests.
// Provides esp_event_base_t (already in esp_websocket_client.h but needed standalone here).

typedef const char* esp_event_base_t;
