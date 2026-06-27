#pragma once

#include <cstdint>

/// Abstract display interface. Implemented per board.
class Display {
public:
    virtual ~Display() = default;

    /// Initialize the display hardware.
    virtual bool init() = 0;

    /// Show connection status ("Connecting...", "Connected", "Disconnected").
    virtual void showStatus(const char* status) = 0;

    /// Show user transcript text.
    virtual void showUserText(const char* text) = 0;

    /// Show assistant response text (streamed — may be called multiple times).
    virtual void showAssistantText(const char* text) = 0;

    /// Show thinking/processing indicator.
    virtual void showThinking(bool active) = 0;

    /// Show error message.
    virtual void showError(const char* error) = 0;

    /// Clear the display.
    virtual void clear() = 0;

    /// Poll whether the push-to-talk button is currently pressed.
    /// Returns false on displays without touch input (e.g. serial stub).
    virtual bool pollPressed() { return false; }
};
