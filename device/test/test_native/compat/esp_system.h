#pragma once

// Minimal esp_system.h for native tests.
// esp_restart() is a no-op in tests (factoryReset calls it).

void esp_restart();
