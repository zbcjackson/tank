#pragma once

#include <cstdint>

/// Abstract hardware abstraction layer for board-specific initialization.
/// Each target (CoreS3, Pyramid) provides a concrete implementation.
class BoardHAL {
public:
    virtual ~BoardHAL() = default;

    /// Initialize all board hardware (I2C, I2S, codec, display, touch).
    virtual bool init() = 0;

    /// Set speaker volume (0–100).
    virtual void setVolume(uint8_t volume) = 0;

    /// Set microphone gain (0–100).
    virtual void setMicGain(uint8_t gain) = 0;

    /// Get the I2S port number used for microphone input.
    virtual int getMicI2SPort() = 0;

    /// Get the I2S port number used for speaker output.
    virtual int getSpkI2SPort() = 0;
};

/// Factory function — returns the correct HAL for the compile-time target.
BoardHAL* createBoardHAL();
