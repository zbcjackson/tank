#pragma once

// Reset ESP stubs state (currently just resets the MAC address to default).
void esp_stubs_reset();

// Set the MAC address returned by esp_read_mac in tests.
void esp_stubs_set_mac(const uint8_t mac[6]);
