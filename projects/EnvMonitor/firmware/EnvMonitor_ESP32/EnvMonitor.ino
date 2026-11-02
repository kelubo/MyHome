/*
 * EnvMonitor - 便携式环境监测仪
 * 版本: v1.0
 * 日期: 2026-04-29
 */

#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <DHT.h>
#include <Preferences.h>

// =============================================
// 显示配置
// =============================================
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);

// =============================================
// 传感器引脚
// =============================================
#define CO_SENSOR_PIN 34
#define H2S_SENSOR_PIN 35
#define DHT_PIN 4
#define BUZZER_PIN 5
#define LED_R 18
#define LED_G 19
#define LED_B 21
#define POWER_KEY 39

// =============================================
// 对象
// =============================================
DHT dht(DHT_PIN, DHT11);
Preferences preferences;

// =============================================
// 阈值
// =============================================
float CO_WARNING = 25.0;
float CO_DANGER = 50.0;
float H2S_WARNING = 10.0;
float H2S_DANGER = 20.0;

// =============================================
// 状态
// =============================================
enum Screen {
    SCREEN_SPLASH,
    SCREEN_MAIN,
    SCREEN_MENU,
    SCREEN_SETTINGS
};

Screen currentScreen = SCREEN_SPLASH;
int menuIndex = 0;
bool alarmMuted = false;
unsigned long lastUpdate = 0;
unsigned long splashStart = 0;

// 传感器数据
float co = 0;
float h2s = 0;
float temp = 0;
float hum = 0;

// =============================================
// 初始化
// =============================================
void setup() {
    Serial.begin(115200);

    pinMode(POWER_KEY, INPUT);
    pinMode(BUZZER_PIN, OUTPUT);
    pinMode(LED_R, OUTPUT);
    pinMode(LED_G, OUTPUT);
    pinMode(LED_B, OUTPUT);

    digitalWrite(BUZZER_PIN, LOW);
    setLED(0, 255, 0);

    Wire.begin();
    if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
        Serial.println("OLED初始化失败");
        while (1);
    }

    display.clearDisplay();
    display.display();

    dht.begin();

    // 读取保存的设置
    preferences.begin("envmon", false);
    CO_WARNING = preferences.getFloat("co_warn", 25.0);
    CO_DANGER = preferences.getFloat("co_danger", 50.0);
    H2S_WARNING = preferences.getFloat("h2s_warn", 10.0);
    H2S_DANGER = preferences.getFloat("h2s_danger", 20.0);
    preferences.end();

    splashStart = millis();
    currentScreen = SCREEN_SPLASH;

    Serial.println("EnvMonitor 初始化完成");
}

// =============================================
// 主循环
// =============================================
void loop() {
    switch (currentScreen) {
        case SCREEN_SPLASH:
            showSplash();
            break;
        case SCREEN_MAIN:
            updateMain();
            break;
        case SCREEN_MENU:
            handleMenu();
            break;
        case SCREEN_SETTINGS:
            handleSettings();
            break;
    }

    checkAlarm();
    delay(100);
}

// =============================================
// 开机画面
// =============================================
void showSplash() {
    display.clearDisplay();
    display.setTextSize(2);
    display.setTextColor(SSD1306_WHITE);
    display.setCursor(20, 20);
    display.println("Env");
    display.setCursor(10, 40);
    display.println("Monitor");
    display.setTextSize(1);
    display.setCursor(40, 56);
    display.println("v1.0");
    display.display();

    if (millis() - splashStart > 2000) {
        currentScreen = SCREEN_MAIN;
    }
}

// =============================================
// 主界面
// =============================================
void updateMain() {
    if (millis() - lastUpdate > 1000) {
        readSensors();

        display.clearDisplay();
        display.setTextSize(1);
        display.setTextColor(SSD1306_WHITE);

        // 标题
        display.setCursor(0, 0);
        display.println("=== EnvMonitor ===");

        // CO
        display.setCursor(0, 16);
        display.print("CO:  ");
        display.print(co, 1);
        display.print(" ppm  ");
        if (co >= CO_DANGER) display.print("[!]");
        else if (co >= CO_WARNING) display.print("[*]");
        else display.print("[OK]");

        // H2S
        display.setCursor(0, 28);
        display.print("H2S: ");
        display.print(h2s, 1);
        display.print(" ppm  ");
        if (h2s >= H2S_DANGER) display.print("[!]");
        else if (h2s >= H2S_WARNING) display.print("[*]");
        else display.print("[OK]");

        // 温湿度
        display.setCursor(0, 40);
        display.print("T: ");
        display.print(temp, 1);
        display.print("C  H: ");
        display.print(hum, 0);
        display.print("%");

        // 状态栏
        display.setCursor(0, 52);
        if (alarmMuted) display.print("[MUTED] ");
        display.print("MENU:KEY  ");
        display.print(millis() / 1000);
        display.print("s");

        display.display();
        lastUpdate = millis();
    }

    // 按键检测
    if (digitalRead(POWER_KEY) == HIGH) {
        delay(50);
        if (digitalRead(POWER_KEY) == HIGH) {
            currentScreen = SCREEN_MENU;
        }
        while (digitalRead(POWER_KEY) == HIGH);
    }
}

// =============================================
// 读取传感器
// =============================================
void readSensors() {
    // CO
    int rawCO = analogRead(CO_SENSOR_PIN);
    float voltage = rawCO * (5.0 / 4095.0);
    float rs = (5.0 - voltage) * 10.0 / voltage;
    float ratio = rs / 10.0;
    co = (ratio > 0.1 && ratio < 10.0) ? 15.0 * pow(ratio, -0.8) : 0;

    // H2S
    int rawH2S = analogRead(H2S_SENSOR_PIN);
    voltage = rawH2S * (5.0 / 4095.0);
    rs = (5.0 - voltage) * 10.0 / voltage;
    ratio = rs / 10.0;
    h2s = (ratio > 0.1 && ratio < 10.0) ? 10.0 * pow(ratio, -0.8) : 0;

    // DHT
    hum = dht.readHumidity();
    temp = dht.readTemperature();
    if (isnan(hum) || isnan(temp)) {
        hum = 0;
        temp = 0;
    }
}

// =============================================
// 检查报警
// =============================================
void checkAlarm() {
    if (alarmMuted) {
        setLED(0, 255, 0);
        digitalWrite(BUZZER_PIN, LOW);
        return;
    }

    if (co >= CO_DANGER || h2s >= H2S_DANGER) {
        setLED(255, 0, 0);
        digitalWrite(BUZZER_PIN, HIGH);
    }
    else if (co >= CO_WARNING || h2s >= H2S_WARNING) {
        setLED(255, 255, 0);
        static unsigned long lastBeep = 0;
        if (millis() - lastBeep > 500) {
            digitalWrite(BUZZER_PIN, !digitalRead(BUZZER_PIN));
            lastBeep = millis();
        }
    }
    else {
        setLED(0, 255, 0);
        digitalWrite(BUZZER_PIN, LOW);
    }
}

// =============================================
// 设置LED
// =============================================
void setLED(int r, int g, int b) {
    digitalWrite(LED_R, r > 0 ? HIGH : LOW);
    digitalWrite(LED_G, g > 0 ? HIGH : LOW);
    digitalWrite(LED_B, b > 0 ? HIGH : LOW);
}

// =============================================
// 菜单
// =============================================
void handleMenu() {
    const char* menuItems[] = {"返回监测", "静音", "设置阈值", "关于"};
    int menuCount = 4;

    display.clearDisplay();
    display.setTextSize(1);
    display.setTextColor(SSD1306_WHITE);

    display.setCursor(0, 0);
    display.println("== 菜单 ==");

    for (int i = 0; i < menuCount; i++) {
        display.setCursor(0, 16 + i * 12);
        if (i == menuIndex) display.print("> ");
        else display.print("  ");
        display.println(menuItems[i]);
    }

    display.display();

    // 简单按键处理
    delay(200);
    if (Serial.available()) {
        char cmd = Serial.read();
        if (cmd == 'w' && menuIndex > 0) menuIndex--;
        if (cmd == 's' && menuIndex < menuCount - 1) menuIndex++;
        if (cmd == '\n') {
            if (menuIndex == 0) currentScreen = SCREEN_MAIN;
            else if (menuIndex == 1) alarmMuted = !alarmMuted;
            else if (menuIndex == 2) currentScreen = SCREEN_SETTINGS;
            else if (menuIndex == 3) showAbout();
        }
    }
}

// =============================================
// 设置界面
// =============================================
void handleSettings() {
    display.clearDisplay();
    display.setTextSize(1);
    display.setTextColor(SSD1306_WHITE);

    display.setCursor(0, 0);
    display.println("== 阈值设置 ==");

    display.setCursor(0, 16);
    display.print("CO W:"); display.print(CO_WARNING, 0);
    display.print(" D:"); display.println(CO_DANGER, 0);

    display.setCursor(0, 28);
    display.print("H2S W:"); display.print(H2S_WARNING, 0);
    display.print(" D:"); display.println(H2S_DANGER, 0);

    display.setCursor(0, 50);
    display.println("保存:S  返回:X");

    display.display();

    delay(200);
    if (Serial.available()) {
        char cmd = Serial.read();
        if (cmd == 'x' || cmd == 'X') {
            currentScreen = SCREEN_MAIN;
        }
        if (cmd == 's' || cmd == 'S') {
            saveSettings();
        }
    }
}

// =============================================
// 保存设置
// =============================================
void saveSettings() {
    preferences.begin("envmon", false);
    preferences.putFloat("co_warn", CO_WARNING);
    preferences.putFloat("co_danger", CO_DANGER);
    preferences.putFloat("h2s_warn", H2S_WARNING);
    preferences.putFloat("h2s_danger", H2S_DANGER);
    preferences.end();

    display.clearDisplay();
    display.setTextSize(2);
    display.setCursor(20, 25);
    display.println("Saved!");
    display.display();
    delay(1000);
    currentScreen = SCREEN_MAIN;
}

// =============================================
// 关于
// =============================================
void showAbout() {
    display.clearDisplay();
    display.setTextSize(1);
    display.setCursor(0, 10);
    display.println("EnvMonitor v1.0");
    display.println("");
    display.println("Portable Environment");
    display.println("Monitoring Device");
    display.println("");
    display.println("Sensors:");
    display.println("- MQ-7 (CO)");
    display.println("- MQ-136 (H2S)");
    display.println("- DHT11 (T/H)");
    display.display();

    delay(3000);
    currentScreen = SCREEN_MAIN;
}