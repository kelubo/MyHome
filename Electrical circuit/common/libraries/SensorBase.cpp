/*
 * 传感器基类 - 实现
 * 版本: v1.0
 * 日期: 2026-04-29
 */

#include "SensorBase.h"

SensorBase::SensorBase(const char* name) {
    sensorName = name;
    status = SENSOR_OK;
    calibrationOffset = 0.0f;
    sampleCount = 0;
    sumValues = 0.0f;

    data.value = 0.0f;
    data.minValue = 0.0f;
    data.maxValue = 0.0f;
    data.avgValue = 0.0f;
    data.unit = "";
    data.timestamp = 0;
    data.valid = false;
}

SensorBase::~SensorBase() {
}

const char* SensorBase::getName() {
    return sensorName;
}

SensorStatus SensorBase::getStatus() {
    return status;
}

SensorData SensorBase::getData() {
    data.timestamp = millis();
    return data;
}

void SensorBase::setCalibrationOffset(float offset) {
    calibrationOffset = offset;
}

float SensorBase::getCalibrationOffset() {
    return calibrationOffset;
}

void SensorBase::updateStats(float value) {
    sampleCount++;

    if (sampleCount == 1) {
        data.minValue = value;
        data.maxValue = value;
    } else {
        if (value < data.minValue) data.minValue = value;
        if (value > data.maxValue) data.maxValue = value;
    }

    sumValues += value;
    data.avgValue = sumValues / sampleCount;
    data.value = value + calibrationOffset;
    data.valid = true;
}

void SensorBase::resetStats() {
    sampleCount = 0;
    sumValues = 0.0f;
    data.minValue = 0.0f;
    data.maxValue = 0.0f;
    data.avgValue = 0.0f;
}

float SensorBase::getMinValue() {
    return data.minValue;
}

float SensorBase::getMaxValue() {
    return data.maxValue;
}

float SensorBase::getAvgValue() {
    return data.avgValue;
}

int SensorBase::getReadCount() {
    return sampleCount;
}