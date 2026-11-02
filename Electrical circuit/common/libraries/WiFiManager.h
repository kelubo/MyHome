/*
 * WiFi连接管理库
 * 版本: v1.0
 * 日期: 2026-04-29
 */

#ifndef WIFI_MANAGER_H
#define WIFI_MANAGER_H

#include <WiFi.h>

class WiFiManager {
private:
    const char* ssid;
    const char* password;
    unsigned long lastReconnectAttempt;
    int reconnectInterval;
    bool shouldSaveConfig;

public:
    WiFiManager(const char* wifiSsid, const char* wifiPassword);

    bool connect(int timeoutSeconds = 30);
    void disconnect();
    bool isConnected();
    void handle();
    int getSignalStrength();
    String getIPAddress();
    String getMACAddress();

    void setReconnectInterval(int seconds);
    void enableAutoReconnect(bool enable);

    // 事件回调
    void onConnect(void (*callback)());
    void onDisconnect(void (*callback)());
    void onGotIP(void (*callback)(IPAddress));

private:
    void (*connectCallback)();
    void (*disconnectCallback)();
    void (*gotIPCallback)(IPAddress);
    bool autoReconnect;
};

#endif /* WIFI_MANAGER_H */