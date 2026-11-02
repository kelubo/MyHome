/*
 * MQ-136 硫化氢传感器库
 * 版本: v1.0
 * 日期: 2026-04-29
 */

#ifndef MQ136_H
#define MQ136_H

#include <Arduino.h>

// 传感器特性
#define MQ136_RL 10.0           // 负载电阻(kΩ)
#define MQ136_R0 10.0           // 清洁空气中的传感器阻值(kΩ)
#define MQ136_VCC 5.0           // 工作电压(V)

// 校准参数
#define MQ136_CLEAN_AIR_FACTOR 1.0  // 清洁空气系数

class MQ136 {
private:
    uint8_t _pin;
    float _rl;
    float _r0;
    float _voltage;

public:
    MQ136(uint8_t pin);
    void begin();
    float getRawValue();
    float getH2S(float temperature = 25.0);
    float getResistance();
    float getPPM(float a, float b, float c);
    void calibrate(float cleanAirValue);
};

#endif /* MQ136_H */