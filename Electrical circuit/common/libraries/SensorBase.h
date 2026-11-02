/*
 * 传感器基类
 * 版本: v1.0
 * 日期: 2026-04-29
 */

#ifndef SENSOR_BASE_H
#define SENSOR_BASE_H

#include <Arduino.h>

// 统一传感器数据结构
struct SensorData {
    float value;              // 测量值
    float minValue;           // 最小值
    float maxValue;           // 最大值
    float avgValue;           // 平均值
    const char* unit;          // 单位
    unsigned long timestamp;   // 时间戳
    bool valid;               // 数据有效性
};

// 传感器状态
enum SensorStatus {
    SENSOR_OK = 0,
    SENSOR_ERROR = 1,
    SENSOR_TIMEOUT = 2,
    SENSOR_CALIBRATING = 3
};

class SensorBase {
public:
    SensorBase(const char* name);
    virtual ~SensorBase();

    // 纯虚函数 - 子类必须实现
    virtual float read() = 0;
    virtual bool begin() = 0;

    // 通用方法
    const char* getName();
    SensorStatus getStatus();
    SensorData getData();
    void setCalibrationOffset(float offset);
    float getCalibrationOffset();

    // 数据统计
    void resetStats();
    float getMinValue();
    float getMaxValue();
    float getAvgValue();
    int getReadCount();

protected:
    const char* sensorName;
    SensorStatus status;
    SensorData data;

    float calibrationOffset;
    int sampleCount;
    float sumValues;

    void updateStats(float value);
};

// 传感器工厂类
class SensorFactory {
public:
    static SensorBase* createSensor(const char* type);
};

#endif /* SENSOR_BASE_H */