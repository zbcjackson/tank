#pragma once

// Voice Pyramid + AtomS3R pin definitions
// Reference: https://docs.m5stack.com/zh_CN/atom/Echo_Pyramid

// I2S pins (shared bus for mic and speaker via Atom connector)
#define PYRAMID_I2S_BCK_PIN    7
#define PYRAMID_I2S_WS_PIN     8
#define PYRAMID_I2S_DOUT_PIN   6   // Speaker data out (to ES8311 DAC)
#define PYRAMID_I2S_DIN_PIN    5   // Mic data in (from ES7210 ADC)
#define PYRAMID_I2S_MCLK_PIN   -1  // MCLK from Si5351, not GPIO

// I2C for codec/LED control
#define PYRAMID_I2C_SDA_PIN    38
#define PYRAMID_I2C_SCL_PIN    39
#define PYRAMID_I2C_FREQ       400000

// I2C addresses
#define PYRAMID_ES7210_ADDR    0x40  // Mic ADC
#define PYRAMID_ES8311_ADDR    0x18  // Speaker DAC
#define PYRAMID_AW87559_ADDR   0x58  // Class-D amp
#define PYRAMID_SI5351_ADDR    0x60  // Programmable clock

// AtomS3R LCD (small 0.85" 128x128)
#define PYRAMID_LCD_WIDTH      128
#define PYRAMID_LCD_HEIGHT     128

// WS2812 LED ring (28 LEDs, 4 bars of 7)
#define PYRAMID_LED_PIN        35
#define PYRAMID_LED_COUNT      28
