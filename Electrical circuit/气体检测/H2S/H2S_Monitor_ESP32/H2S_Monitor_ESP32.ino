/*
 * 硫化氢监测装置 - ESP32 WiFi版本
 * 版本: v1.0
 * 日期: 2026-04-29
 *
 * 功能：
 * - 实时监测H2S浓度
 * - OLED本地显示
 * - WiFi远程数据传输
 * - Web服务器
 * - MQTT上报
 */

#include <WiFi.h>
#include <WebServer.h>
#include <PubSubClient.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include "MQ136.h"

// WiFi配置
const char* ssid = "YOUR_WIFI_SSID";
const char* password = "YOUR_WIFI_PASSWORD";

// MQTT配置
const char* mqtt_server = "mqtt.example.com";
const int mqtt_port = 1883;
const char* mqtt_topic = "home/h2s";

// 引脚定义
#define H2S_SENSOR_PIN 34        // MQ-136传感器模拟引脚
#define BUZZER_PIN 5             // 蜂鸣器引脚
#define LED_GREEN 18             // 绿色LED
#define LED_YELLOW 19            // 黄色LED
#define LED_RED 21               // 红色LED
#define BUTTON_PIN 22            // 按键引脚

// 报警阈值 (ppm)
#define THRESHOLD_WARNING 10.0
#define THRESHOLD_DANGER 20.0

// 显示配置
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);

// 传感器对象
MQ136 h2sSensor(H2S_SENSOR_PIN);

// 全局对象
WiFiClient espClient;
PubSubClient mqttClient(espClient);
WebServer server(80);

// 全局变量
float h2sConcentration = 0.0;
float temperature = 25.0;
bool alarmMuted = false;
unsigned long lastMqttPublish = 0;
unsigned long lastSensorRead = 0;

/*
 * 初始化WiFi
 */
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

/*
 * 初始化MQTT
 */
void initMQTT() {
    mqttClient.setServer(mqtt_server, mqtt_port);
    mqttClient.setCallback(mqttCallback);
}

/*
 * MQTT回调函数
 */
void mqttCallback(char* topic, byte* payload, unsigned int length) {
    Serial.print("MQTT消息: ");
    for (int i = 0; i < length; i++) {
        Serial.print((char)payload[i]);
    }
    Serial.println();
}

/*
 * 重新连接MQTT
 */
void reconnectMQTT() {
    while (!mqttClient.connected()) {
        Serial.print("连接MQTT服务器...");
        String clientId = "H2S-Monitor-";
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

/*
 * 初始化Web服务器
 */
void initWebServer() {
    server.on("/", handleRoot);
    server.on("/data", handleData);
    server.on("/status", handleStatus);
    server.on("/control", handleControl);
    server.begin();
    Serial.println("Web服务器已启动");
}

/*
 * 网页根目录
 */
void handleRoot() {
    String html = "<html><head><meta charset='utf-8'><title>H2S监测</title>";
    html += "<style>body{font-family:Arial;padding:20px;}";
    html += ".card{background:#f0f0f0;padding:20px;margin:10px 0;border-radius:10px;}";
    html += ".value{font-size:48px;color:#333;}";
    html += ".safe{color:green;}.warn{color:orange;}.danger{color:red;}";
    html += "button{padding:10px 20px;font-size:16px;margin:5px;}";
    html += "</style></head><body>";
    html += "<h1>🏠 硫化氢监测装置</h1>";
    html += "<div class='card'>";
    html += "<div>H2S浓度</div>";
    html += "<div class='value' id='h2s'>" + String(h2sConcentration, 2) + " ppm</div>";
    html += "<div id='status'>" + getStatusText() + "</div>";
    html += "</div>";
    html += "<div class='card'>";
    html += "<p>温度: " + String(temperature, 1) + " °C</p>";
    html += "<p>报警状态: " + String(alarmMuted ? "静音" : "正常") + "</p>";
    html += "<p>WiFi: " + String(WiFi.SSID()) + " (" + String(WiFi.RSSI()) + " dBm)</p>";
    html += "<p>运行时间: " + String(millis() / 1000) + " 秒</p>";
    html += "</div>";
    html += "<button onclick='location.reload()'>刷新</button>";
    html += "<button onclick='toggleMute()'>切换静音</button>";
    html += "<script>";
    html += "function toggleMute(){fetch('/control?action=mute').then(r=>location.reload());}";
    html += "setInterval(()=>fetch('/data').then(r=>r.json()).then(d=>{";
    html += "document.getElementById('h2s').innerHTML=d.h2s+' ppm';";
    html += "document.getElementById('status').innerHTML=d.status;";
    html += "}),5000);";
    html += "</script></body></html>";

    server.send(200, "text/html; charset=utf-8", html);
}

/*
 * 获取数据JSON
 */
void handleData() {
    String json = "{";
    json += "\"h2s\":" + String(h2sConcentration, 2) + ",";
    json += "\"temperature\":" + String(temperature, 1) + ",";
    json += "\"status\":\"" + getStatusText() + "\",";
    json += "\"alarm_muted\":" + String(alarmMuted ? "true" : "false") + ",";
    json += "\"uptime\":" + String(millis() / 1000);
    json += "}";
    server.send(200, "application/json", json);
}

/*
 * 获取状态JSON
 */
void handleStatus() {
    String json = "{";
    json += "\"wifi_rssi\":" + String(WiFi.RSSI()) + ",";
    json += "\"wifi_ssid\":\"" + String(WiFi.SSID()) + "\",";
    json += "\"ip\":\"" + WiFi.localIP().toString() + "\",";
    json += "\"uptime\":" + String(millis() / 1000);
    json += "}";
    server.send(200, "application/json", json);
}

/*
 * 控制接口
 */
void handleControl() {
    if (server.hasArg("action")) {
        String action = server.arg("action");
        if (action == "mute") {
            alarmMuted = !alarmMuted;
        }
    }
    server.send(200, "text/plain", "OK");
}

/*
 * 获取状态文本
 */
String getStatusText() {
    if (h2sConcentration >= THRESHOLD_DANGER) return "<span class='danger'>⚠️ 危险</span>";
    if (h2sConcentration >= THRESHOLD_WARNING) return "<span class='warn'>⚡ 警告</span>";
    return "<span class='safe'>✅ 安全</span>";
}

/*
 * 检查报警
 */
void checkAlarm() {
    if (alarmMuted) {
        digitalWrite(LED_GREEN, HIGH);
        digitalWrite(LED_YELLOW, LOW);
        digitalWrite(LED_RED, LOW);
        digitalWrite(BUZZER_PIN, LOW);
        return;
    }

    if (h2sConcentration >= THRESHOLD_DANGER) {
        digitalWrite(LED_GREEN, LOW);
        digitalWrite(LED_YELLOW, LOW);
        digitalWrite(LED_RED, HIGH);
        digitalWrite(BUZZER_PIN, HIGH);
    }
    else if (h2sConcentration >= THRESHOLD_WARNING) {
        digitalWrite(LED_GREEN, LOW);
        digitalWrite(LED_YELLOW, HIGH);
        digitalWrite(LED_RED, LOW);
        static unsigned long lastBeep = 0;
        if (millis() - lastBeep > 500) {
            digitalWrite(BUZZER_PIN, !digitalRead(BUZZER_PIN));
            lastBeep = millis();
        }
    }
    else {
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

    // 标题
    display.setTextSize(1);
    display.setCursor(0, 0);
    display.println("H2S Monitor v1.0");

    // H2S浓度
    display.setTextSize(2);
    display.setCursor(0, 16);
    display.print(h2sConcentration, 1);
    display.println(" ppm");

    // 状态
    display.setTextSize(1);
    display.setCursor(0, 40);
    if (h2sConcentration >= THRESHOLD_DANGER) display.println("!! DANGER !!");
    else if (h2sConcentration >= THRESHOLD_WARNING) display.println("! WARNING !");
    else display.println("SAFE");

    // WiFi状态
    display.setCursor(0, 52);
    display.print("WiFi:");
    if (WiFi.status() == WL_CONNECTED) {
        display.print(WiFi.RSSI());
        display.print("dBm");
    } else {
        display.print("Disconnected");
    }

    display.display();
}

/*
 * 发布MQTT数据
 */
void publishMQTT() {
    if (!mqttClient.connected()) {
        reconnectMQTT();
    }
    mqttClient.loop();

    if (millis() - lastMqttPublish > 30000) { // 30秒发布一次
        String payload = "{";
        payload += "\"h2s\":" + String(h2sConcentration, 2) + ",";
        payload += "\"temperature\":" + String(temperature, 1) + ",";
        payload += "\"alarm\":" + String(alarmMuted ? "muted" : "normal");
        payload += "}";

        mqttClient.publish(mqtt_topic, payload.c_str());
        lastMqttPublish = millis();
    }
}

/*
 * 初始化函数
 */
void setup() {
    Serial.begin(115200);

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

    // 初始化OLED
    Wire.begin();
    if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
        Serial.println("OLED初始化失败");
    }
    display.clearDisplay();
    display.display();

    // 初始化传感器
    h2sSensor.begin();

    // 初始化WiFi
    initWiFi();

    // 初始化MQTT
    initMQTT();

    // 初始化Web服务器
    initWebServer();

    Serial.println("H2S监测装置初始化完成");
}

/*
 * 主循环
 */
void loop() {
    // 处理Web请求
    server.handleClient();

    // 读取传感器
    if (millis() - lastSensorRead > 1000) {
        h2sConcentration = h2sSensor.getH2S(temperature);
        checkAlarm();
        updateDisplay();
        lastSensorRead = millis();
    }

    // MQTT发布
    publishMQTT();

    // 按键检测
    if (digitalRead(BUTTON_PIN) == LOW) {
        alarmMuted = !alarmMuted;
        delay(200);
    }
}