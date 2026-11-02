/*
 * AirHub - 智能家居网关
 * 版本: v1.0
 * 日期: 2026-04-29
 *
 * 功能：
 * - 多传感器数据采集
 * - OLED本地显示
 * - WiFi远程传输
 * - Web服务器
 * - 报警系统
 */

#include <WiFi.h>
#include <WebServer.h>
#include <PubSubClient.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <DHT.h>

// =============================================
// WiFi和MQTT配置
// =============================================
const char* ssid = "YOUR_WIFI_SSID";
const char* password = "YOUR_WIFI_PASSWORD";
const char* mqtt_server = "mqtt.example.com";
const int mqtt_port = 1883;
const char* mqtt_topic = "home/airhub";

// =============================================
// 传感器引脚定义
// =============================================
#define CO_SENSOR_PIN 34        // MQ-7 一氧化碳
#define H2S_SENSOR_PIN 35        // MQ-136 硫化氢
#define PM25_LED_PIN 13          // GP2Y1010AU LED
#define PM25_SENSOR_PIN 36       // GP2Y1010AU 输出
#define DHT_PIN 4               // DHT11 数据引脚
#define BUZZER_PIN 5            // 蜂鸣器
#define RGB_R 18                // RGB LED 红
#define RGB_G 19                // RGB LED 绿
#define RGB_B 21                // RGB LED 蓝

// =============================================
// 显示配置
// =============================================
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);

// =============================================
// 全局对象
// =============================================
WiFiClient espClient;
PubSubClient mqttClient(espClient);
WebServer server(80);
DHT dht(DHT_PIN, DHT11);

// =============================================
// 传感器数据
// =============================================
struct SensorData {
    float co;           // CO浓度 (ppm)
    float h2s;          // H2S浓度 (ppm)
    float pm25;         // PM2.5 (μg/m³)
    float temperature;  // 温度 (°C)
    float humidity;     // 湿度 (%)
    unsigned long timestamp;
} sensorData;

// =============================================
// 报警状态
// =============================================
enum AlertLevel { ALERT_NONE, ALERT_INFO, ALERT_WARNING, ALERT_DANGER, ALERT_CRITICAL };
AlertLevel currentAlert = ALERT_NONE;
bool alarmMuted = false;

// =============================================
// 时间戳
// =============================================
unsigned long lastSensorRead = 0;
unsigned long lastDisplayUpdate = 0;
unsigned long lastMqttPublish = 0;
unsigned long lastWebUpdate = 0;
const int SENSOR_INTERVAL = 1000;
const int MQTT_INTERVAL = 30000;
const int WEB_UPDATE_INTERVAL = 5000;

// =============================================
// 初始化WiFi
// =============================================
void initWiFi() {
    Serial.print("连接WiFi: ");
    Serial.println(ssid);
    WiFi.mode(WIFI_STA);
    WiFi.begin(ssid, password);

    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 30) {
        delay(500);
        Serial.print(".");
        attempts++;
    }

    if (WiFi.status() == WL_CONNECTED) {
        Serial.println("\nWiFi已连接");
        Serial.print("IP地址: ");
        Serial.println(WiFi.localIP());
    } else {
        Serial.println("\nWiFi连接失败");
    }
}

// =============================================
// 初始化MQTT
// =============================================
void initMQTT() {
    mqttClient.setServer(mqtt_server, mqtt_port);
    mqttClient.setCallback(mqttCallback);
}

void mqttCallback(char* topic, byte* payload, unsigned int length) {
    Serial.print("MQTT消息: ");
    for (int i = 0; i < length; i++) Serial.print((char)payload[i]);
    Serial.println();
}

void reconnectMQTT() {
    while (!mqttClient.connected()) {
        Serial.print("连接MQTT...");
        String clientId = "AirHub-";
        clientId += String(WiFi.localIP());

        if (mqttClient.connect(clientId.c_str())) {
            Serial.println("已连接");
            mqttClient.subscribe(mqtt_topic);
        } else {
            Serial.print("失败, rc=");
            Serial.print(mqttClient.state());
            delay(5000);
        }
    }
}

// =============================================
// 初始化Web服务器
// =============================================
void initWebServer() {
    server.on("/", handleRoot);
    server.on("/api/data", handleData);
    server.on("/api/status", handleStatus);
    server.on("/api/alerts", handleAlerts);
    server.on("/api/control", handleControl);
    server.begin();
    Serial.println("Web服务器已启动");
}

// =============================================
// 读取CO传感器
// =============================================
float readCO() {
    int raw = analogRead(CO_SENSOR_PIN);
    float voltage = raw * (5.0 / 4095.0);
    float rs = (5.0 - voltage) * 10.0 / voltage;
    float ratio = rs / 10.0;
    float ppm = 0.0;

    if (ratio > 0.1 && ratio < 10.0) {
        ppm = 15.0 * pow(ratio, -0.8);
    }

    return ppm;
}

// =============================================
// 读取H2S传感器
// =============================================
float readH2S() {
    int raw = analogRead(H2S_SENSOR_PIN);
    float voltage = raw * (5.0 / 4095.0);
    float rs = (5.0 - voltage) * 10.0 / voltage;
    float ratio = rs / 10.0;
    float ppm = 0.0;

    if (ratio > 0.1 && ratio < 10.0) {
        ppm = 10.0 * pow(ratio, -0.8);
    }

    return ppm;
}

// =============================================
// 读取PM2.5传感器
// =============================================
float readPM25() {
    digitalWrite(PM25_LED_PIN, LOW);
    delayMicroseconds(280);

    int raw = analogRead(PM25_SENSOR_PIN);

    digitalWrite(PM25_LED_PIN, HIGH);
    delayMicroseconds(40);

    float voltage = raw * (5.0 / 4095.0);
    float dustDensity = voltage * 0.17 * 100.0;

    return max(0.0, dustDensity);
}

// =============================================
// 读取温湿度
// =============================================
void readDHT() {
    sensorData.humidity = dht.readHumidity();
    sensorData.temperature = dht.readTemperature();

    if (isnan(sensorData.humidity) || isnan(sensorData.temperature)) {
        sensorData.humidity = 0;
        sensorData.temperature = 0;
    }
}

// =============================================
// 读取所有传感器
// =============================================
void readAllSensors() {
    sensorData.co = readCO();
    sensorData.h2s = readH2S();
    sensorData.pm25 = readPM25();
    readDHT();
    sensorData.timestamp = millis();

    Serial.printf("CO: %.1f ppm, H2S: %.1f ppm, PM2.5: %.1f μg/m³, Temp: %.1f°C, Hum: %.1f%%\n",
                   sensorData.co, sensorData.h2s, sensorData.pm25,
                   sensorData.temperature, sensorData.humidity);
}

// =============================================
// 检查报警
// =============================================
void checkAlerts() {
    if (alarmMuted) {
        setRGB(0, 255, 0);  // 绿色
        return;
    }

    float maxValue = max(max(sensorData.co / 25.0, sensorData.h2s / 10.0), sensorData.pm25 / 75.0);

    if (maxValue >= 4.0) {
        currentAlert = ALERT_CRITICAL;
        setRGB(255, 0, 0);  // 红色
        digitalWrite(BUZZER_PIN, HIGH);
    }
    else if (maxValue >= 2.0) {
        currentAlert = ALERT_DANGER;
        setRGB(255, 0, 0);
        static unsigned long lastBeep = 0;
        if (millis() - lastBeep > 500) {
            digitalWrite(BUZZER_PIN, !digitalRead(BUZZER_PIN));
            lastBeep = millis();
        }
    }
    else if (maxValue >= 1.0) {
        currentAlert = ALERT_WARNING;
        setRGB(255, 255, 0);  // 黄色
        digitalWrite(BUZZER_PIN, LOW);
    }
    else {
        currentAlert = ALERT_NONE;
        setRGB(0, 255, 0);  // 绿色
        digitalWrite(BUZZER_PIN, LOW);
    }
}

// =============================================
// 设置RGB LED
// =============================================
void setRGB(int r, int g, int b) {
    digitalWrite(RGB_R, r > 0 ? HIGH : LOW);
    digitalWrite(RGB_G, g > 0 ? HIGH : LOW);
    digitalWrite(RGB_B, b > 0 ? HIGH : LOW);
}

// =============================================
// 更新OLED显示
// =============================================
void updateDisplay() {
    display.clearDisplay();
    display.setTextColor(SSD1306_WHITE);

    display.setTextSize(1);
    display.setCursor(0, 0);
    display.println("AirHub Monitor");

    display.setTextSize(1);
    display.setCursor(0, 16);
    display.printf("CO:  %.1f ppm", sensorData.co);
    display.setCursor(70, 16);
    display.printf("H2S: %.1f", sensorData.h2s);

    display.setCursor(0, 28);
    display.printf("PM2.5: %.0f ug/m3", sensorData.pm25);

    display.setCursor(0, 40);
    display.printf("Temp: %.1f C", sensorData.temperature);
    display.setCursor(70, 40);
    display.printf("Hum:  %.0f%%", sensorData.humidity);

    display.setCursor(0, 52);
    display.printf("Status: ");
    switch (currentAlert) {
        case ALERT_NONE: display.print("SAFE"); break;
        case ALERT_WARNING: display.print("WARNING"); break;
        case ALERT_DANGER: display.print("DANGER"); break;
        case ALERT_CRITICAL: display.print("CRITICAL!"); break;
        default: display.print("UNKNOWN");
    }

    display.display();
}

// =============================================
// Web页面
// =============================================
void handleRoot() {
    String html = "<!DOCTYPE html><html><head>";
    html += "<meta charset='utf-8'><title>AirHub</title>";
    html += "<style>";
    html += "body{font-family:Arial;padding:20px;background:#f0f0f0;}";
    html += ".card{background:white;padding:20px;margin:10px 0;border-radius:10px;box-shadow:0 2px 5px rgba(0,0,0,0.1);}";
    html += ".value{font-size:36px;color:#333;}";
    html += ".safe{color:green;}.warning{color:orange;}.danger{color:red;}";
    html += ".grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;}";
    html += "button{padding:10px 20px;background:#007bff;color:white;border:none;border-radius:5px;cursor:pointer;}";
    html += "button:hover{background:#0056b3;}";
    html += ".mute{background:#6c757d;}";
    html += "</style></head><body>";
    html += "<h1>🏠 AirHub 智能家居网关</h1>";

    html += "<div class='grid'>";
    html += "<div class='card'><div>CO 一氧化碳</div><div class='value'>" + String(sensorData.co, 1) + " <small>ppm</small></div></div>";
    html += "<div class='card'><div>H2S 硫化氢</div><div class='value'>" + String(sensorData.h2s, 1) + " <small>ppm</small></div></div>";
    html += "<div class='card'><div>PM2.5</div><div class='value'>" + String(sensorData.pm25, 0) + " <small>μg/m³</small></div></div>";
    html += "<div class='card'><div>温湿度</div><div class='value'>" + String(sensorData.temperature, 1) + "°C <small>/</small> " + String(sensorData.humidity, 0) + "%</div></div>";
    html += "</div>";

    html += "<div class='card'>";
    html += "<h3>状态: <span id='status'></span></h3>";
    html += "<p>WiFi信号: " + String(WiFi.RSSI()) + " dBm | 运行时间: <span id='uptime'></span>秒</p>";
    html += "<button onclick='location.reload()'>刷新</button>";
    html += "<button class='mute' onclick='toggleMute()'>静音</button>";
    html += "</div>";

    html += "<script>";
    html += "function getStatus(){";
    html += "fetch('/api/data').then(r=>r.json()).then(d=>{";
    html += "document.getElementById('status').innerHTML=d.alert_text;";
    html += "document.getElementById('uptime').innerHTML=Math.floor(d.uptime/1000);";
    html += "});}";
    html += "function toggleMute(){fetch('/api/control?action=mute').then(r=>location.reload());}";
    html += "getStatus();setInterval(getStatus,5000);";
    html += "</script></body></html>";

    server.send(200, "text/html; charset=utf-8", html);
}

// =============================================
// API: 获取数据
// =============================================
void handleData() {
    String alert_text = "SAFE";
    if (currentAlert == ALERT_WARNING) alert_text = "WARNING";
    else if (currentAlert == ALERT_DANGER) alert_text = "DANGER";
    else if (currentAlert == ALERT_CRITICAL) alert_text = "CRITICAL";

    String json = "{";
    json += "\"co\":" + String(sensorData.co, 2) + ",";
    json += "\"h2s\":" + String(sensorData.h2s, 2) + ",";
    json += "\"pm25\":" + String(sensorData.pm25, 2) + ",";
    json += "\"temperature\":" + String(sensorData.temperature, 2) + ",";
    json += "\"humidity\":" + String(sensorData.humidity, 2) + ",";
    json += "\"alert\":" + String(currentAlert) + ",";
    json += "\"alert_text\":\"" + alert_text + "\",";
    json += "\"uptime\":" + String(millis()) + ",";
    json += "\"wifi_rssi\":" + String(WiFi.RSSI());
    json += "}";

    server.send(200, "application/json", json);
}

// =============================================
// API: 获取状态
// =============================================
void handleStatus() {
    String json = "{";
    json += "\"wifi_ssid\":\"" + String(WiFi.SSID()) + "\",";
    json += "\"wifi_rssi\":" + String(WiFi.RSSI()) + ",";
    json += "\"ip\":\"" + WiFi.localIP().toString() + "\",";
    json += "\"uptime\":" + String(millis() / 1000) + ",";
    json += "\"firmware\":\"v1.0\"";
    json += "}";
    server.send(200, "application/json", json);
}

// =============================================
// API: 获取报警
// =============================================
void handleAlerts() {
    String alert_text = "无报警";
    if (currentAlert == ALERT_WARNING) alert_text = "警告";
    else if (currentAlert == ALERT_DANGER) alert_text = "危险";
    else if (currentAlert == ALERT_CRITICAL) alert_text = "紧急";

    String json = "[{";
    json += "\"level\":" + String(currentAlert) + ",";
    json += "\"text\":\"" + alert_text + "\",";
    json += "\"timestamp\":" + String(millis());
    json += "}]";
    server.send(200, "application/json", json);
}

// =============================================
// API: 控制
// =============================================
void handleControl() {
    if (server.hasArg("action")) {
        String action = server.arg("action");
        if (action == "mute") alarmMuted = !alarmMuted;
    }
    server.send(200, "text/plain", "OK");
}

// =============================================
// MQTT发布
// =============================================
void publishMQTT() {
    if (!mqttClient.connected()) {
        reconnectMQTT();
    }
    mqttClient.loop();

    if (millis() - lastMqttPublish > MQTT_INTERVAL) {
        String payload = "{";
        payload += "\"co\":" + String(sensorData.co, 2) + ",";
        payload += "\"h2s\":" + String(sensorData.h2s, 2) + ",";
        payload += "\"pm25\":" + String(sensorData.pm25, 2) + ",";
        payload += "\"temperature\":" + String(sensorData.temperature, 2) + ",";
        payload += "\"humidity\":" + String(sensorData.humidity, 2);
        payload += "}";

        mqttClient.publish(mqtt_topic, payload.c_str());
        lastMqttPublish = millis();
    }
}

// =============================================
// 初始化
// =============================================
void setup() {
    Serial.begin(115200);

    pinMode(BUZZER_PIN, OUTPUT);
    pinMode(RGB_R, OUTPUT);
    pinMode(RGB_G, OUTPUT);
    pinMode(RGB_B, OUTPUT);
    pinMode(PM25_LED_PIN, OUTPUT);
    pinMode(PM25_SENSOR_PIN, INPUT);

    digitalWrite(BUZZER_PIN, LOW);
    digitalWrite(PM25_LED_PIN, HIGH);
    setRGB(0, 0, 0);

    Wire.begin();
    if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
        Serial.println("OLED初始化失败");
    }
    display.clearDisplay();
    display.display();

    dht.begin();

    initWiFi();
    initMQTT();
    initWebServer();

    Serial.println("AirHub 初始化完成");
}

// =============================================
// 主循环
// =============================================
void loop() {
    server.handleClient();

    if (millis() - lastSensorRead > SENSOR_INTERVAL) {
        readAllSensors();
        checkAlerts();
        updateDisplay();
        lastSensorRead = millis();
    }

    publishMQTT();

    delay(10);
}