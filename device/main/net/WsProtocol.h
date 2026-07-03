#pragma once

// Protocol parsing functions extracted from WsClient for testability.
// These are pure functions with no ESP-IDF dependencies (only cJSON for JSON parsing).

#include <cstdint>
#include <cstddef>

struct WsMessage;  // Forward declaration (defined in WsClient.h)

/// Parsed audio frame header.
struct AudioFrameHeader {
    uint16_t magic;
    uint32_t sample_rate;
    uint16_t channels;
};

/// Parse an audio frame header from raw bytes.
/// Returns true if header is valid (correct magic, sufficient length).
/// On success, populates `out` with parsed fields.
bool parseAudioFrameHeader(const uint8_t* data, int len, AudioFrameHeader* out);

/// Parse a JSON WebSocket message into a WsMessage struct.
/// Returns true on successful parse. Handles missing optional fields gracefully.
/// Requires cJSON at link time.
bool parseWsJsonMessage(const char* data, int len, WsMessage* out);
