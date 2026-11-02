/*
 * MQ-136 硫化氢传感器库
 * 版本: v1.0
 * 日期: 2026-04-29
 */

#include "MQ136.h"
#include <Arduino.h>

MQ136::MQ136(uint8_t pin) {
    _pin = pin;
    _rl = MQ136_RL;
    _r0 = MQ136_R0;
}

/*
 * 初始化传感器
 */
void MQ136::begin() {
    pinMode(_pin, INPUT);
    calibrate(MQ136_CLEAN_AIR_FACTOR);
}

/*
 * 获取原始ADC值
 */
float MQ136::getRawValue() {
    int adcValue = analogRead(_pin);
    _voltage = adcValue * (5.0 / 1023.0);
    return _voltage;
}

/*
 * 获取传感器电阻值
 */
float MQ136::getResistance() {
    getRawValue();
    // 计算传感器电阻: Rs = (Vcc - Vout) * RL / Vout
    float rs = (MQ136_VCC - _voltage) * _rl / _voltage;
    return rs;
}

/*
 * 获取H2S浓度 (ppm)
 * 使用指数曲线进行转换
 */
float MQ136::getH2S(float temperature) {
    float rs = getResistance();
    float ratio = rs / _r0;
    
    // 根据传感器特性曲线计算ppm
    // MQ-136 H2S曲线近似: y = a * x^b
    // 使用对数线性化: log(y) = log(a) + b * log(x)
    
    // 温度补偿
    float tempFactor = 1.0 + 0.02 * (temperature - 20.0);
    
    // H2S浓度计算（使用经验公式）
    // 参考曲线: 在清洁空气中ratio约1.0，在10ppm时ratio约0.8
    float ppm = 0.0;
    
    if (ratio > 0.1 && ratio < 10.0) {
        // 使用近似指数曲线
        // y = a * x^b
        // 其中 x = ratio, y = ppm
        float a = 15.0;   // 系数
        float b = -0.8;  // 指数
        
        ppm = a * pow(ratio, b);
        
        // 应用温度补偿
        ppm = ppm / tempFactor;
    }
    
    return ppm;
}

/*
 * 使用幂函数计算ppm
 */
float MQ136::getPPM(float a, float b, float c) {
    float rs = getResistance();
    float ratio = rs / _r0;
    
    // 使用通用幂函数: ppm = a * (ratio)^b + c
    float ppm = a * pow(ratio, b) + c;
    
    if (ppm < 0) ppm = 0;
    
    return ppm;
}

/*
 * 校准传感器
 * 在清洁空气中测量，将当前读数设为基准值
 */
void MQ136::calibrate(float cleanAirValue) {
    // 在清洁空气中连续采样多次取平均
    float sum = 0;
    int samples = 100;
    
    for (int i = 0; i < samples; i++) {
        sum += getResistance();
        delay(10);
    }
    
    float avgRs = sum / samples;
    _r0 = avgRs / cleanAirValue;
}