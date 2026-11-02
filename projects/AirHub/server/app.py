# AirHub 后端服务
# 版本: v1.0
# 日期: 2026-04-29

from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import json

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///airhub.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# =============================================
# 数据库模型
# =============================================

class Device(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), default='AirHub')
    location = db.Column(db.String(100))
    ip_address = db.Column(db.String(45))
    status = db.Column(db.String(20), default='offline')
    last_seen = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'location': self.location,
            'ip_address': self.ip_address,
            'status': self.status,
            'last_seen': self.last_seen.isoformat() if self.last_seen else None
        }


class SensorReading(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.Integer, db.ForeignKey('device.id'))
    co = db.Column(db.Float)          # CO ppm
    h2s = db.Column(db.Float)         # H2S ppm
    pm25 = db.Column(db.Float)       # PM2.5 μg/m³
    temperature = db.Column(db.Float) # 温度 °C
    humidity = db.Column(db.Float)    # 湿度 %
    alert_level = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'device_id': self.device_id,
            'co': self.co,
            'h2s': self.h2s,
            'pm25': self.pm25,
            'temperature': self.temperature,
            'humidity': self.humidity,
            'alert_level': self.alert_level,
            'created_at': self.created_at.isoformat()
        }


class Alert(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.Integer, db.ForeignKey('device.id'))
    sensor = db.Column(db.String(20))
    level = db.Column(db.Integer)  # 0=none, 1=info, 2=warning, 3=danger, 4=critical
    message = db.Column(db.String(500))
    value = db.Column(db.Float)
    threshold = db.Column(db.Float)
    resolved = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'device_id': self.device_id,
            'sensor': self.sensor,
            'level': self.level,
            'message': self.message,
            'value': self.value,
            'threshold': self.threshold,
            'resolved': self.resolved,
            'created_at': self.created_at.isoformat()
        }


class Threshold(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sensor = db.Column(db.String(20), unique=True)
    warning = db.Column(db.Float)
    danger = db.Column(db.Float)
    critical = db.Column(db.Float)

    def to_dict(self):
        return {
            'sensor': self.sensor,
            'warning': self.warning,
            'danger': self.danger,
            'critical': self.critical
        }


# 初始化数据库
with app.app_context():
    db.create_all()

    # 添加默认阈值
    if not Threshold.query.filter_by(sensor='co').first():
        thresholds = [
            Threshold(sensor='co', warning=25.0, danger=50.0, critical=100.0),
            Threshold(sensor='h2s', warning=10.0, danger=20.0, critical=50.0),
            Threshold(sensor='pm25', warning=75.0, danger=150.0, critical=250.0),
        ]
        for t in thresholds:
            db.session.add(t)
        db.session.commit()


# =============================================
# 设备管理 API
# =============================================

@app.route('/api/devices', methods=['GET'])
def get_devices():
    devices = Device.query.all()
    return jsonify([d.to_dict() for d in devices])


@app.route('/api/devices/<int:device_id>', methods=['GET'])
def get_device(device_id):
    device = Device.query.get_or_404(device_id)
    return jsonify(device.to_dict())


@app.route('/api/devices', methods=['POST'])
def create_device():
    data = request.get_json()
    device = Device(
        name=data.get('name', 'AirHub'),
        location=data.get('location', 'Home')
    )
    db.session.add(device)
    db.session.commit()
    return jsonify(device.to_dict()), 201


@app.route('/api/devices/<int:device_id>', methods=['PUT'])
def update_device(device_id):
    device = Device.query.get_or_404(device_id)
    data = request.get_json()

    if 'name' in data:
        device.name = data['name']
    if 'location' in data:
        device.location = data['location']
    if 'ip_address' in data:
        device.ip_address = data['ip_address']
    if 'status' in data:
        device.status = data['status']

    device.last_seen = datetime.utcnow()
    db.session.commit()
    return jsonify(device.to_dict())


# =============================================
# 数据 API
# =============================================

@app.route('/api/data', methods=['GET'])
def get_all_data():
    limit = int(request.args.get('limit', 100))
    device_id = request.args.get('device_id', type=int)

    query = SensorReading.query
    if device_id:
        query = query.filter_by(device_id=device_id)

    readings = query.order_by(SensorReading.created_at.desc()).limit(limit).all()
    return jsonify([r.to_dict() for r in readings])


@app.route('/api/data/latest', methods=['GET'])
def get_latest_data():
    device_id = request.args.get('device_id', type=int)

    query = SensorReading.query
    if device_id:
        query = query.filter_by(device_id=device_id)

    latest = query.order_by(SensorReading.created_at.desc()).first()
    if latest:
        return jsonify(latest.to_dict())
    return jsonify({'error': 'No data'}), 404


@app.route('/api/data/<int:device_id>', methods=['POST'])
def upload_data(device_id):
    data = request.get_json()

    reading = SensorReading(
        device_id=device_id,
        co=data.get('co', 0),
        h2s=data.get('h2s', 0),
        pm25=data.get('pm25', 0),
        temperature=data.get('temperature', 0),
        humidity=data.get('humidity', 0),
        alert_level=data.get('alert_level', 0)
    )
    db.session.add(reading)

    # 更新设备状态
    device = Device.query.get(device_id)
    if device:
        device.status = 'online'
        device.last_seen = datetime.utcnow()

    # 检查报警
    check_alerts(device_id, data)

    db.session.commit()
    return jsonify({'message': 'Data uploaded successfully'}), 201


@app.route('/api/data/<sensor>/stats', methods=['GET'])
def get_sensor_stats(sensor):
    hours = int(request.args.get('hours', 24))
    since = datetime.utcnow() - timedelta(hours=hours)

    readings = SensorReading.query.filter(
        SensorReading.created_at >= since
    ).all()

    if not readings:
        return jsonify({'error': 'No data'}), 404

    values = [getattr(r, sensor) for r in readings if getattr(r, sensor) is not None]

    return jsonify({
        'sensor': sensor,
        'count': len(values),
        'min': min(values) if values else 0,
        'max': max(values) if values else 0,
        'avg': sum(values) / len(values) if values else 0
    })


# =============================================
# 报警 API
# =============================================

def check_alerts(device_id, data):
    thresholds = Threshold.query.all()

    for threshold in thresholds:
        value = data.get(threshold.sensor, 0)
        level = 0
        alert_threshold = 0

        if value >= threshold.critical:
            level = 4
            alert_threshold = threshold.critical
        elif value >= threshold.danger:
            level = 3
            alert_threshold = threshold.danger
        elif value >= threshold.warning:
            level = 2
            alert_threshold = threshold.warning

        if level > 0:
            alert = Alert(
                device_id=device_id,
                sensor=threshold.sensor,
                level=level,
                message=f'{threshold.sensor.upper()} {level_to_text(level)}: {value}',
                value=value,
                threshold=alert_threshold
            )
            db.session.add(alert)


def level_to_text(level):
    texts = {0: '正常', 1: '信息', 2: '警告', 3: '危险', 4: '紧急'}
    return texts.get(level, '未知')


@app.route('/api/alerts', methods=['GET'])
def get_alerts():
    resolved = request.args.get('resolved', 'false').lower() == 'true'
    device_id = request.args.get('device_id', type=int)

    query = Alert.query.filter_by(resolved=resolved)
    if device_id:
        query = query.filter_by(device_id=device_id)

    alerts = query.order_by(Alert.created_at.desc()).limit(100).all()
    return jsonify([a.to_dict() for a in alerts])


@app.route('/api/alerts/<int:alert_id>', methods=['PUT'])
def resolve_alert(alert_id):
    alert = Alert.query.get_or_404(alert_id)
    alert.resolved = True
    db.session.commit()
    return jsonify({'message': 'Alert resolved'})


@app.route('/api/alerts/resolve_all', methods=['POST'])
def resolve_all_alerts():
    device_id = request.args.get('device_id', type=int)
    query = Alert.query.filter_by(resolved=False)
    if device_id:
        query = query.filter_by(device_id=device_id)

    count = query.update({'resolved': True})
    db.session.commit()
    return jsonify({'resolved_count': count})


# =============================================
# 阈值配置 API
# =============================================

@app.route('/api/thresholds', methods=['GET'])
def get_thresholds():
    thresholds = Threshold.query.all()
    return jsonify([t.to_dict() for t in thresholds])


@app.route('/api/thresholds/<sensor>', methods=['PUT'])
def update_threshold(sensor):
    threshold = Threshold.query.filter_by(sensor=sensor).first_or_404()
    data = request.get_json()

    if 'warning' in data:
        threshold.warning = data['warning']
    if 'danger' in data:
        threshold.danger = data['danger']
    if 'critical' in data:
        threshold.critical = data['critical']

    db.session.commit()
    return jsonify(threshold.to_dict())


# =============================================
# 健康检查
# =============================================

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'version': 'v1.0'
    })


@app.route('/api/stats', methods=['GET'])
def get_stats():
    device_count = Device.query.count()
    reading_count = SensorReading.query.count()
    alert_count = Alert.query.filter_by(resolved=False).count()

    return jsonify({
        'devices': device_count,
        'readings': reading_count,
        'active_alerts': alert_count
    })


# =============================================
# 启动服务
# =============================================

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)