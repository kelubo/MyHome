/*
 * MyHome 共享库索引
 * 版本: v1.0
 * 日期: 2026-04-29
 *
 * 使用方法:
 * 将此文件夹复制到 Arduino libraries 目录
 * 或在项目中使用完整路径 #include "common/libraries/xxx.h"
 */

#ifndef COMMON_LIBRARIES_H
#define COMMON_LIBRARIES_H

/*
 * 已包含的库:
 * - OLEDHelper.h    : OLED显示辅助
 * - WiFiManager.h   : WiFi连接管理
 * - SensorBase.h    : 传感器基类
 * - AlertManager.h  : 报警管理
 */

/*
 * 快速使用示例:

#include "common/libraries/OLEDHelper.h"
#include "common/libraries/WiFiManager.h"
#include "common/libraries/SensorBase.h"
#include "common/libraries/AlertManager.h"

// 创建OLED对象
OLEDHelper oled;

// 创建WiFi管理器
WiFiManager wifi("SSID", "PASSWORD");

// 创建报警管理器
AlertManager alerts(BUZZER_PIN, LED_PIN);

// 在setup()中初始化
void setup() {
    oled.begin(0x3C);
    wifi.connect();
    alerts.setThreshold(10.0, 20.0, 30.0);
}

// 在loop()中使用
void loop() {
    float value = readSensor();
    oled.printFloat(0, 0, value, 2, 2);
    alerts.check(value);
}

*/

#endif /* COMMON_LIBRARIES_H */