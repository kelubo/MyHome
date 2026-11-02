/*
 * OLED显示辅助库 - 实现
 * 版本: v1.0
 * 日期: 2026-04-29
 */

#include "OLEDHelper.h"

OLEDHelper::OLEDHelper(uint8_t width, uint8_t height) {
    display = new Adafruit_SSD1306(width, height, &Wire, -1);
    initialized = false;
}

bool OLEDHelper::begin(uint8_t i2cAddr) {
    Wire.begin();
    if (!display->begin(SSD1306_SWITCHCAPVCC, i2cAddr)) {
        return false;
    }
    display->clearDisplay();
    display->setTextColor(SSD1306_WHITE);
    initialized = true;
    return true;
}

void OLEDHelper::clear() {
    if (initialized) {
        display->clearDisplay();
    }
}

void OLEDHelper::update() {
    if (initialized) {
        display->display();
    }
}

void OLEDHelper::printText(uint8_t x, uint8_t y, const char *text, uint8_t size) {
    if (!initialized) return;
    display->setTextSize(size);
    display->setCursor(x, y);
    display->println(text);
}

void OLEDHelper::printFloat(uint8_t x, uint8_t y, float value, uint8_t decimals, uint8_t size) {
    if (!initialized) return;
    display->setTextSize(size);
    display->setCursor(x, y);
    display->println(value, decimals);
}

void OLEDHelper::printInt(uint8_t x, uint8_t y, int value, uint8_t size) {
    if (!initialized) return;
    display->setTextSize(size);
    display->setCursor(x, y);
    display->println(value);
}

void OLEDHelper::drawProgressBar(uint8_t x, uint8_t y, uint8_t width, uint8_t height, float percent) {
    if (!initialized) return;
    percent = constrain(percent, 0, 100);

    display->drawRect(x, y, width, height, SSD1306_WHITE);
    uint8_t fillWidth = (width - 2) * percent / 100;
    display->fillRect(x + 1, y + 1, fillWidth, height - 2, SSD1306_WHITE);
}

void OLEDHelper::drawGauge(uint8_t x, uint8_t y, uint8_t radius, float value, float minVal, float maxVal) {
    if (!initialized) return;
    float angle = map(value, minVal, maxVal, -135, 135);
    display->drawCircle(x, y, radius, SSD1306_WHITE);
    // 绘制指针
    float rad = angle * PI / 180;
    int tipX = x + (radius - 5) * cos(rad);
    int tipY = y + (radius - 5) * sin(rad);
    display->drawLine(x, y, tipX, tipY, SSD1306_WHITE);
}

void OLEDHelper::drawIcon(uint8_t x, uint8_t y, const uint8_t *icon, uint8_t w, uint8_t h) {
    if (!initialized) return;
    display->drawBitmap(x, y, icon, w, h, SSD1306_WHITE);
}

void OLEDHelper::displayHeader(const char *title) {
    clear();
    printText(0, 0, title, 1);
    display->drawLine(0, 10, 128, 10, SSD1306_WHITE);
    update();
}

void OLEDHelper::displayValue(const char *label, float value, const char *unit) {
    printText(0, 20, label, 1);
    printText(0, 35, String(value).c_str(), 2);
    printText(80, 35, unit, 1);
    update();
}

void OLEDHelper::displayStatus(const char *status, bool isWarning) {
    if (isWarning) {
        display->setTextColor(SSD1306_BLACK, SSD1306_WHITE);
    }
    printText(0, 50, status, 1);
    display->setTextColor(SSD1306_WHITE);
    update();
}