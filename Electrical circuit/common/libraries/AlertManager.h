/*
 * 报警管理模块
 * 版本: v1.0
 * 日期: 2026-04-29
 */

#ifndef ALERT_MANAGER_H
#define ALERT_MANAGER_H

#include <Arduino.h>

// 报警级别
enum AlertLevel {
    ALERT_NONE = 0,
    ALERT_INFO = 1,
    ALERT_WARNING = 2,
    ALERT_DANGER = 3,
    ALERT_CRITICAL = 4
};

// 报警信息结构
struct Alert {
    AlertLevel level;
    const char* message;
    unsigned long timestamp;
    bool acknowledged;
};

// 报警回调函数类型
typedef void (*AlertCallback)(Alert);

// 报警阈值配置
struct ThresholdConfig {
    float warning;
    float danger;
    float critical;
};

class AlertManager {
private:
    static const int MAX_ALERTS = 10;
    Alert alerts[MAX_ALERTS];
    int alertCount;
    unsigned long lastAlertTime;
    int alertCooldown;

    AlertCallback alertCallback;
    bool buzzerEnabled;
    int buzzerPin;
    int ledPin;

    ThresholdConfig threshold;

public:
    AlertManager(int buzzer = 8, int led = 6);

    void setThreshold(float warning, float danger, float critical);
    void setCooldown(int milliseconds);
    void onAlert(AlertCallback callback);

    void check(float value);
    void check(const char* sensorName, float value, float warning, float danger);

    AlertLevel getCurrentLevel();
    const char* getLevelText(AlertLevel level);
    bool hasActiveAlert();
    int getActiveAlertCount();

    void acknowledgeAll();
    void clearAll();
};

#endif /* ALERT_MANAGER_H */