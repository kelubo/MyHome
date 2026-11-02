/*
 * 报警管理模块 - 实现
 * 版本: v1.0
 * 日期: 2026-04-29
 */

#include "AlertManager.h"

AlertManager::AlertManager() {
    alertCount = 0;
    lastAlertTime = 0;
    alertCooldown = 5000;
    alertCallback = nullptr;
    buzzerEnabled = true;
    ledEnabled = true;

    threshold.warning = 10.0;
    threshold.danger = 20.0;
    threshold.critical = 30.0;
}

void AlertManager::setThreshold(float warning, float danger, float critical) {
    threshold.warning = warning;
    threshold.danger = danger;
    threshold.critical = critical;
}

void AlertManager::setCooldown(int milliseconds) {
    alertCooldown = milliseconds;
}

void AlertManager::onAlert(AlertCallback callback) {
    alertCallback = callback;
}

void AlertManager::enableBuzzer(bool enable) {
    buzzerEnabled = enable;
}

void AlertManager::enableLed(bool enable) {
    ledEnabled = enable;
}

void AlertManager::check(float value) {
    check("Sensor", value, threshold.warning, threshold.danger);
}

void AlertManager::check(const char* sensorName, float value, float warning, float danger) {
    AlertLevel newLevel = ALERT_NONE;

    if (value >= threshold.critical) {
        newLevel = ALERT_CRITICAL;
    } else if (value >= threshold.danger) {
        newLevel = ALERT_DANGER;
    } else if (value >= threshold.warning) {
        newLevel = ALERT_WARNING;
    }

    if (newLevel != ALERT_NONE) {
        // 检查冷却时间
        if (millis() - lastAlertTime > alertCooldown) {
            char msg[100];
            snprintf(msg, sizeof(msg), "%s: %.1f", sensorName, value);
            triggerAlert(newLevel, msg);
            lastAlertTime = millis();
        }
    }
}

AlertLevel AlertManager::getCurrentLevel() {
    if (alertCount == 0) return ALERT_NONE;

    AlertLevel maxLevel = ALERT_NONE;
    for (int i = 0; i < alertCount; i++) {
        if (!alerts[i].acknowledged && alerts[i].level > maxLevel) {
            maxLevel = alerts[i].level;
        }
    }
    return maxLevel;
}

const char* AlertManager::getLevelText(AlertLevel level) {
    switch (level) {
        case ALERT_NONE: return "正常";
        case ALERT_INFO: return "信息";
        case ALERT_WARNING: return "警告";
        case ALERT_DANGER: return "危险";
        case ALERT_CRITICAL: return "紧急";
        default: return "未知";
    }
}

bool AlertManager::hasActiveAlert() {
    return getCurrentLevel() != ALERT_NONE;
}

int AlertManager::getActiveAlertCount() {
    int count = 0;
    for (int i = 0; i < alertCount; i++) {
        if (!alerts[i].acknowledged) count++;
    }
    return count;
}

void AlertManager::acknowledgeAll() {
    for (int i = 0; i < alertCount; i++) {
        alerts[i].acknowledged = true;
    }
}

void AlertManager::clearAll() {
    alertCount = 0;
}

void AlertManager::triggerBuzzer(int durationMs) {
    if (buzzerEnabled) {
        digitalWrite(BUZZER_PIN, HIGH);
        delay(durationMs);
        digitalWrite(BUZZER_PIN, LOW);
    }
}

void AlertManager::triggerAlert(AlertLevel level, const char* message) {
    if (alertCount < MAX_ALERTS) {
        alerts[alertCount].level = level;
        alerts[alertCount].message = message;
        alerts[alertCount].timestamp = millis();
        alerts[alertCount].acknowledged = false;
        alertCount++;
    }

    if (alertCallback) {
        Alert a = {level, message, millis(), false};
        alertCallback(a);
    }
}