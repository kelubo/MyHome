/*
 * 硫化氢监测装置 - 主程序
 * 版本: v1.0
 * 日期: 2026-04-29
 */

#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include "MQ136.h"

// 引脚定义
#define H2S_SENSOR_PIN A0        // MQ-136传感器模拟引脚
#define BUZZER_PIN 8             // 蜂鸣器引脚
#define LED_GREEN 4             // 绿色LED
#define LED_YELLOW 5            // 黄色LED
#define LED_RED 6               // 红色LED
#define BUTTON_PIN 7            // 按键引脚

// 报警阈值 (ppm)
#define THRESHOLD_WARNING 10.0   // 警告阈值
#define THRESHOLD_DANGER 20.0    // 危险阈值

// 显示配置
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
#define OLED_RESET -1
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);

// 传感器对象
MQ136 h2sSensor(H2S_SENSOR_PIN);

// 全局变量
float h2sConcentration = 0.0;    // H2S浓度
float temperature = 25.0;         // 温度补偿
unsigned long lastUpdate = 0;    // 上次更新时间
bool alarmMuted = false;          // 报警静音标志

/*
 * 初始化函数
 */
void setup() {
    Serial.begin(9600);
    
    // 初始化引脚
    pinMode(BUZZER_PIN, OUTPUT);
    pinMode(LED_GREEN, OUTPUT);
    pinMode(LED_YELLOW, OUTPUT);
    pinMode(LED_RED, OUTPUT);
    pinMode(BUTTON_PIN, INPUT_PULLUP);
    
    // 关闭所有LED和蜂鸣器
    digitalWrite(BUZZER_PIN, LOW);
    digitalWrite(LED_GREEN, LOW);
    digitalWrite(LED_YELLOW, LOW);
    digitalWrite(LED_RED, LOW);
    
    // 初始化OLED显示屏
    Wire.begin();
    if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
        Serial.println("OLED初始化失败");
        while (1);
    }
    
    display.clearDisplay();
    display.setTextColor(SSD1306_WHITE);
    display.setTextSize(2);
    display.println("H2S Monitor");
    display.setTextSize(1);
    display.println("Initializing...");
    display.display();
    
    delay(2000);
    
    Serial.println("硫化氢监测装置初始化完成");
}

/*
 * 主循环
 */
void loop() {
    // 读取H2S浓度
    h2sConcentration = h2sSensor.getH2S(temperature);
    
    // 检查报警状态
    checkAlarm();
    
    // 更新显示
    updateDisplay();
    
    // 检查按钮（静音功能）
    if (digitalRead(BUTTON_PIN) == LOW) {
        alarmMuted = !alarmMuted;
        delay(200);
    }
    
    // 串口输出
    if (millis() - lastUpdate > 1000) {
        Serial.print("H2S: ");
        Serial.print(h2sConcentration);
        Serial.println(" ppm");
        lastUpdate = millis();
    }
    
    delay(100);
}

/*
 * 检查报警状态
 */
void checkAlarm() {
    if (alarmMuted) {
        // 静音模式下关闭所有报警
        digitalWrite(LED_GREEN, HIGH);
        digitalWrite(LED_YELLOW, LOW);
        digitalWrite(LED_RED, LOW);
        digitalWrite(BUZZER_PIN, LOW);
        return;
    }
    
    if (h2sConcentration >= THRESHOLD_DANGER) {
        // 危险级别 - 红色LED + 持续蜂鸣
        digitalWrite(LED_GREEN, LOW);
        digitalWrite(LED_YELLOW, LOW);
        digitalWrite(LED_RED, HIGH);
        digitalWrite(BUZZER_PIN, HIGH);
    }
    else if (h2sConcentration >= THRESHOLD_WARNING) {
        // 警告级别 - 黄色LED + 间歇蜂鸣
        digitalWrite(LED_GREEN, LOW);
        digitalWrite(LED_YELLOW, HIGH);
        digitalWrite(LED_RED, LOW);
        
        // 间歇蜂鸣
        static unsigned long lastBeep = 0;
        if (millis() - lastBeep > 500) {
            digitalWrite(BUZZER_PIN, !digitalRead(BUZZER_PIN));
            lastBeep = millis();
        }
    }
    else {
        // 安全级别 - 绿色LED
        digitalWrite(LED_GREEN, HIGH);
        digitalWrite(LED_YELLOW, LOW);
        digitalWrite(LED_RED, LOW);
        digitalWrite(BUZZER_PIN, LOW);
    }
}

/*
 * 更新OLED显示
 */
void updateDisplay() {
    display.clearDisplay();
    display.setTextColor(SSD1306_WHITE);
    
    // 显示标题
    display.setTextSize(1);
    display.setCursor(0, 0);
    display.println("H2S Monitor v1.0");
    
    // 显示浓度值
    display.setTextSize(3);
    display.setCursor(0, 16);
    display.print(h2sConcentration, 1);
    display.setTextSize(1);
    display.print(" ppm");
    
    // 显示状态
    display.setTextSize(1);
    display.setCursor(0, 48);
    if (alarmMuted) {
        display.print("[MUTED] ");
    }
    
    if (h2sConcentration >= THRESHOLD_DANGER) {
        display.setTextColor(SSD1306_BLACK, SSD1306_WHITE);
        display.print(" DANGER!");
    }
    else if (h2sConcentration >= THRESHOLD_WARNING) {
        display.print(" WARNING");
    }
    else {
        display.print(" SAFE");
    }
    
    // 显示温度
    display.setTextColor(SSD1306_WHITE);
    display.setCursor(100, 0);
    display.print(temperature, 0);
    display.print("C");
    
    display.display();
}