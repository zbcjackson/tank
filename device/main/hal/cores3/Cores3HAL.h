#pragma once

#include "../BoardHAL.h"
#include "es7210.h"

class Cores3HAL : public BoardHAL {
public:
    bool init() override;
    void setVolume(uint8_t volume) override;
    void setMicGain(uint8_t gain) override;
    int getMicI2SPort() override;
    int getSpkI2SPort() override;

private:
    bool initI2C();
    bool initPMU();         // AXP2101 power management
    bool initIOExpander();  // AW9523B IO expander
    bool initMicCodec();    // ES7210
    bool initAmpCodec();    // AW88298
    bool initI2S();

    bool axp2101SetVoltage(uint8_t reg, int voltage_mv);
    bool axp2101EnableLDO(uint8_t voltage_reg);

    es7210_dev_handle_t es7210_handle_ = nullptr;
    uint8_t volume_ = 70;
    uint8_t mic_gain_ = 50;
};
