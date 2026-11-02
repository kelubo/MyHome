# MyHome 完整项目

本文档总览 `projects/` 目录下的完整项目。

## AirHub - 智能家居网关

**位置**: `AirHub/`

一款整合多种传感器数据的智能家居网关，支持数据采集、报警、远程监控和自动控制。

### 特性

- 多传感器整合（CO、H2S、PM2.5、温湿度）
- OLED本地显示 + Web远程查看
- WiFi远程传输 + MQTT协议
- 智能报警系统
- RESTful API接口

### 快速开始

```bash
# 烧录固件
cd AirHub/firmware/AirHub_ESP32
pio run -t upload

# 启动后端服务
cd AirHub/server
pip install flask flask-sqlalchemy
python app.py

# 访问Web界面
http://<设备IP>
```

---

## EnvMonitor - 便携式环境监测仪

**位置**: `EnvMonitor/`

一款便携式手持环境监测仪，适合现场检测和移动作业。

### 特性

- 多参数检测（CO、H2S、温度、湿度）
- 便携手持设计
- 电池供电，约8小时续航
- OLED实时显示
- 声光报警
- 阈值可配置

### 规格

| 参数 | 数值 |
|------|------|
| 尺寸 | 150 x 80 x 30 mm |
| 重量 | 约200g |
| 电池 | 3.7V 2000mAh |
| 续航 | 约8小时 |

---

## 项目规划

### 计划中

| 项目 | 说明 | 状态 |
|------|------|------|
| AirQualityStation | 空气质量监测站 | ✅ 已完成 |
| PortableMonitor | 便携式监测仪 | ✅ 已完成 |
| SmartHomeHub | 智能家居控制中心 | 📋 规划中 |
| DataLogger | 数据记录器 | 📋 规划中 |
| RemoteController | 远程控制器 | 📋 规划中 |

### 待添加功能

- [ ] 微信/钉钉推送集成
- [ ] 数据导出功能（CSV/Excel）
- [ ] 历史数据图表分析
- [ ] 设备联动控制
- [ ] 固件OTA升级
- [ ] 多语言支持

---

## 硬件参考

### ESP32 开发板选型

| 型号 | 特点 | 适用场景 |
|------|------|----------|
| ESP32-WROOM-32 | 通用型 | 大部分场景 |
| ESP32-S3 | 双核+Xtensa | 需要更多算力 |
| ESP32-C3 | RISC-V, 低功耗 | 电池供电 |

### 传感器兼容性

所有项目均使用通用传感器，兼容以下主控：

- Arduino Uno/Nano
- ESP32-DevKit
- ESP32-S3-DevKit
- Raspberry Pi Pico

---

## 技术栈

| 类别 | 技术 |
|------|------|
| 固件 | Arduino, ESP-IDF, PlatformIO |
| 通信 | WiFi, MQTT, HTTP |
| 后端 | Flask, SQLite |
| 前端 | HTML5, CSS3, JavaScript, Chart.js |
| 数据存储 | SQLite, SPIFFS |

---

**最后更新**: 2026-04-29