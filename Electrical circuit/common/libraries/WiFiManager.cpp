/*
 * WiFi连接管理库 - 实现
 * 版本: v1.0
 * 日期: 2026-04-29
 */

#include "WiFiManager.h"

WiFiManager::WiFiManager(const char* wifiSsid, const char* wifiPassword) {
    ssid = wifiSsid;
    password = wifiPassword;
    reconnectInterval = 5000;
    lastReconnectAttempt = 0;
    shouldSaveConfig = false;
    autoReconnect = true;
    connectCallback = nullptr;
    disconnectCallback = nullptr;
    gotIPCallback = nullptr;
}

bool WiFiManager::connect(int timeoutSeconds) {
    Serial.print("连接WiFi: ");
    Serial.println(ssid);

    WiFi.mode(WIFI_STA);
    WiFi.begin(ssid, password);

    unsigned long startTime = millis();
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");

        if (millis() - startTime > timeoutSeconds * 1000) {
            Serial.println("\n连接超时");
            return false;
        }
    }

    Serial.println("\nWiFi已连接");
    Serial.print("IP地址: ");
    Serial.println(WiFi.localIP());

    if (connectCallback) {
        connectCallback();
    }

    if (gotIPCallback) {
        gotIPCallback(WiFi.localIP());
    }

    return true;
}

void WiFiManager::disconnect() {
    WiFi.disconnect();
}

bool WiFiManager::isConnected() {
    return WiFi.status() == WL_CONNECTED;
}

void WiFiManager::handle() {
    if (!isConnected() && autoReconnect) {
        if (millis() - lastReconnectAttempt > reconnectInterval) {
            lastReconnectAttempt = millis();
            Serial.println("WiFi断开，正在重连...");
            connect();
        }
    }
}

int WiFiManager::getSignalStrength() {
    return WiFi.RSSI();
}

String WiFiManager::getIPAddress() {
    return WiFi.localIP().toString();
}

String WiFiManager::getMACAddress() {
    return WiFi.macAddress();
}

void WiFiManager::setReconnectInterval(int seconds) {
    reconnectInterval = seconds * 1000;
}

void WiFiManager::enableAutoReconnect(bool enable) {
    autoReconnect = enable;
}

void WiFiManager::onConnect(void (*callback)()) {
    connectCallback = callback;
}

void WiFiManager::onDisconnect(void (*callback)()) {
    disconnectCallback = callback;
}

void WiFiManager::onGotIP(void (*callback)(IPAddress)) {
    gotIPCallback = callback;
}