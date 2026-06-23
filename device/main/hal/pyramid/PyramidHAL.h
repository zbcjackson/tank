#pragma once

#include "../BoardHAL.h"

class PyramidHAL : public BoardHAL {
public:
    bool init() override;
    void setVolume(uint8_t volume) override;
    void setMicGain(uint8_t gain) override;
    int getMicI2SPort() override;
    int getSpkI2SPort() override;

private:
    bool initI2C();
    bool initClock();      // Si5351
    bool initMicCodec();   // ES7210
    bool initDacCodec();   // ES8311
    bool initAmp();        // AW87559
    bool initI2S();

    uint8_t volume_ = 70;
    uint8_t mic_gain_ = 50;
};
