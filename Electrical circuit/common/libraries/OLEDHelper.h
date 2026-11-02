/*
 * OLED显示辅助库
 * 版本: v1.0
 * 日期: 2026-04-29
 */

#ifndef OLED_HELPER_H
#define OLED_HELPER_H

#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

class OLEDHelper {
private:
    Adafruit_SSD1306 *display;
    bool initialized;

public:
    OLEDHelper(uint8_t width = 128, uint8_t height = 64);
    bool begin(uint8_t i2cAddr = 0x3C);
    void clear();
    void update();

    // 文字显示
    void printText(uint8_t x, uint8_t y, const char *text, uint8_t size = 1);
    void printFloat(uint8_t x, uint8_t y, float value, uint8_t decimals, uint8_t size = 2);
    void printInt(uint8_t x, uint8_t y, int value, uint8_t size = 2);

    // 图形显示
    void drawProgressBar(uint8_t x, uint8_t y, uint8_t width, uint8_t height, float percent);
    void drawGauge(uint8_t x, uint8_t y, uint8_t radius, float value, float minVal, float maxVal);
    void drawIcon(uint8_t x, uint8_t y, const uint8_t *icon, uint8_t w, uint8_t h);

    // 格式化显示
    void displayHeader(const char *title);
    void displayValue(const char *label, float value, const char *unit);
    void displayStatus(const char *status, bool isWarning = false);
};

#endif /* OLED_HELPER_H */