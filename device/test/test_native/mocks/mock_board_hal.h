#pragma once

// GMock implementation of the BoardHAL interface.
// Use in tests that verify Assistant → HAL interactions (volume, mic gain).

#include <gmock/gmock.h>
#include "hal/BoardHAL.h"

class MockBoardHAL : public BoardHAL {
public:
    MOCK_METHOD(bool, init, (), (override));
    MOCK_METHOD(void, setVolume, (uint8_t volume), (override));
    MOCK_METHOD(void, setMicGain, (uint8_t gain), (override));
    MOCK_METHOD(int, getMicI2SPort, (), (override));
    MOCK_METHOD(int, getSpkI2SPort, (), (override));
};
