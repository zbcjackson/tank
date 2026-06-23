#pragma once

// CoreS3 I2S pin definitions
// Reference: https://docs.m5stack.com/zh_CN/core/CoreS3

#define CORES3_I2S_BCK_PIN    34
#define CORES3_I2S_WS_PIN     33
#define CORES3_I2S_DOUT_PIN   13  // Speaker data out
#define CORES3_I2S_DIN_PIN    14  // Mic data in
#define CORES3_I2S_MCLK_PIN   0

// I2C for codec control (ES7210 mic, AW88298 amp)
#define CORES3_I2C_SDA_PIN    12
#define CORES3_I2C_SCL_PIN    11
#define CORES3_I2C_FREQ       400000

// ES7210 mic codec I2C address
#define CORES3_ES7210_ADDR    0x40

// AW88298 amplifier I2C address
#define CORES3_AW88298_ADDR   0x36

// Display (ILI9342C) SPI pins
#define CORES3_LCD_CS_PIN     3
#define CORES3_LCD_DC_PIN     35
#define CORES3_LCD_RST_PIN    -1
#define CORES3_LCD_BL_PIN     -1
#define CORES3_LCD_WIDTH      320
#define CORES3_LCD_HEIGHT     240

// Touch (FT6336U) I2C
#define CORES3_TOUCH_ADDR     0x38
