# AirHub API 文档

## 版本

- API版本: v1.0
- 更新日期: 2026-04-29

## 基础URL

```
http://localhost:5000/api
```

## 设备管理

### 获取设备列表

```
GET /api/devices
```

响应示例:
```json
[
  {
    "id": 1,
    "name": "AirHub",
    "location": "Home",
    "ip_address": "192.168.1.100",
    "status": "online",
    "last_seen": "2026-04-29T12:00:00"
  }
]
```

### 获取设备详情

```
GET /api/devices/:id
```

### 创建设备

```
POST /api/devices
```

请求体:
```json
{
  "name": "AirHub",
  "location": "Home"
}
```

### 更新设备

```
PUT /api/devices/:id
```

请求体:
```json
{
  "name": "AirHub Living Room",
  "location": "Living Room",
  "status": "online"
}
```

## 数据接口

### 获取所有数据

```
GET /api/data
```

查询参数:
| 参数 | 类型 | 说明 |
|------|------|------|
| limit | int | 返回记录数，默认100 |
| device_id | int | 设备ID |

响应示例:
```json
[
  {
    "id": 1,
    "device_id": 1,
    "co": 12.5,
    "h2s": 5.2,
    "pm25": 35.0,
    "temperature": 25.5,
    "humidity": 60.0,
    "alert_level": 0,
    "created_at": "2026-04-29T12:00:00"
  }
]
```

### 获取最新数据

```
GET /api/data/latest
```

查询参数:
| 参数 | 类型 | 说明 |
|------|------|------|
| device_id | int | 设备ID |

响应示例:
```json
{
  "id": 100,
  "device_id": 1,
  "co": 12.5,
  "h2s": 5.2,
  "pm25": 35.0,
  "temperature": 25.5,
  "humidity": 60.0,
  "alert_level": 0,
  "created_at": "2026-04-29T12:05:00"
}
```

### 上传数据

```
POST /api/data/:device_id
```

请求体:
```json
{
  "co": 12.5,
  "h2s": 5.2,
  "pm25": 35.0,
  "temperature": 25.5,
  "humidity": 60.0,
  "alert_level": 0
}
```

### 获取传感器统计

```
GET /api/data/:sensor/stats
```

查询参数:
| 参数 | 类型 | 说明 |
|------|------|------|
| hours | int | 统计时间范围（小时），默认24 |

响应示例:
```json
{
  "sensor": "co",
  "count": 1440,
  "min": 5.2,
  "max": 45.0,
  "avg": 15.3
}
```

## 报警接口

### 获取报警列表

```
GET /api/alerts
```

查询参数:
| 参数 | 类型 | 说明 |
|------|------|------|
| resolved | bool | 是否已解决，默认false |
| device_id | int | 设备ID |

响应示例:
```json
[
  {
    "id": 1,
    "device_id": 1,
    "sensor": "co",
    "level": 2,
    "message": "CO 警告: 35.0",
    "value": 35.0,
    "threshold": 25.0,
    "resolved": false,
    "created_at": "2026-04-29T12:00:00"
  }
]
```

### 解决报警

```
PUT /api/alerts/:id
```

### 批量解决报警

```
POST /api/alerts/resolve_all
```

查询参数:
| 参数 | 类型 | 说明 |
|------|------|------|
| device_id | int | 设备ID（可选） |

## 阈值配置

### 获取所有阈值

```
GET /api/thresholds
```

响应示例:
```json
[
  {
    "sensor": "co",
    "warning": 25.0,
    "danger": 50.0,
    "critical": 100.0
  },
  {
    "sensor": "h2s",
    "warning": 10.0,
    "danger": 20.0,
    "critical": 50.0
  },
  {
    "sensor": "pm25",
    "warning": 75.0,
    "danger": 150.0,
    "critical": 250.0
  }
]
```

### 更新阈值

```
PUT /api/thresholds/:sensor
```

请求体:
```json
{
  "warning": 30.0,
  "danger": 60.0,
  "critical": 120.0
}
```

## 系统接口

### 健康检查

```
GET /api/health
```

响应示例:
```json
{
  "status": "healthy",
  "timestamp": "2026-04-29T12:00:00",
  "version": "v1.0"
}
```

### 系统统计

```
GET /api/stats
```

响应示例:
```json
{
  "devices": 1,
  "readings": 1000,
  "active_alerts": 2
}
```

## 报警级别

| level | 名称 | 说明 |
|-------|------|------|
| 0 | 正常 | 无报警 |
| 1 | 信息 | 提示信息 |
| 2 | 警告 | 需要注意 |
| 3 | 危险 | 需要处理 |
| 4 | 紧急 | 立即处理 |

## 错误码

| 错误码 | 说明 |
|--------|------|
| 200 | 成功 |
| 400 | 请求参数错误 |
| 404 | 资源不存在 |
| 500 | 服务器内部错误 |