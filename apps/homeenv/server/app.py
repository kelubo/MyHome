import os
from datetime import datetime, date, timedelta

from flask import Flask, request, jsonify, abort

try:
    from flask_sqlalchemy import SQLAlchemy
    HAVE_SQLA = True
except Exception:
    HAVE_SQLA = False

app = Flask(__name__)
# 集成模式由 docker-compose 注入 DATABASE_URL（PostgreSQL）；本地缺省回退到 SQLite 文件
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///./homeenv.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app) if HAVE_SQLA else None


# ───────────────────────── 数据模型 ─────────────────────────
class EnvRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room = db.Column(db.String(60), nullable=False, default='客厅')   # 房间/区域
    recorded_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    temperature = db.Column(db.Float, nullable=True)                  # 温度 ℃
    humidity = db.Column(db.Float, nullable=True)                    # 湿度 %
    pm25 = db.Column(db.Integer, nullable=True)                      # PM2.5 μg/m³
    co2 = db.Column(db.Integer, nullable=True)                       # CO2 ppm
    notes = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ───────────────────────── 工具 ─────────────────────────
def _parse_dt(s):
    if isinstance(s, datetime):
        return s
    s = str(s).replace('T', ' ').strip()
    try:
        return datetime.strptime(s[:19], '%Y-%m-%d %H:%M:%S')
    except Exception:
        try:
            return datetime.strptime(s[:10], '%Y-%m-%d')
        except Exception:
            return None


def _f(v):
    return round(float(v), 1) if v is not None else None


def _rec_json(r):
    return {
        'id': r.id, 'room': r.room or '',
        'recorded_at': r.recorded_at.isoformat() if r.recorded_at else '',
        'temperature': _f(r.temperature), 'humidity': _f(r.humidity),
        'pm25': r.pm25, 'co2': r.co2, 'notes': r.notes or '',
        'created_at': r.created_at.isoformat() if r.created_at else None,
    }


# ───────────────────────── 通用 ─────────────────────────
@app.after_request
def _cors(resp):
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Access-Control-Allow-Methods'] = 'GET,POST,PUT,DELETE,OPTIONS'
    resp.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return resp


@app.route('/health')
def health():
    return jsonify(ok=True, counts={'records': EnvRecord.query.count()} if HAVE_SQLA else {'records': 0})


# ───────────────────────── 环境记录 ─────────────────────────
@app.route('/records', methods=['GET'])
def list_records():
    q = (request.args.get('q') or '').strip()
    room = (request.args.get('room') or '').strip()
    query = EnvRecord.query
    if room:
        query = query.filter_by(room=room)
    if q:
        like = f'%{q}%'
        query = query.filter(EnvRecord.notes.ilike(like))
    rows = query.order_by(EnvRecord.recorded_at.desc()).all()
    return jsonify([_rec_json(r) for r in rows])


@app.route('/rooms', methods=['GET'])
def list_rooms():
    # 每个房间的最新一条记录 + 记录数
    from sqlalchemy import func
    rooms = db.session.query(EnvRecord.room, func.count(EnvRecord.id)).group_by(EnvRecord.room).all()
    out = []
    for room, cnt in rooms:
        latest = EnvRecord.query.filter_by(room=room).order_by(EnvRecord.recorded_at.desc()).first()
        out.append({
            'room': room, 'count': cnt,
            'latest': _rec_json(latest) if latest else None,
        })
    out.sort(key=lambda x: -x['count'])
    return jsonify(out)


@app.route('/stats', methods=['GET'])
def stats():
    rows = EnvRecord.query.all()
    temps = [r.temperature for r in rows if r.temperature is not None]
    hums = [r.humidity for r in rows if r.humidity is not None]
    rooms = db.session.query(EnvRecord.room).distinct().all()
    return jsonify({
        'total': len(rows),
        'rooms': len(rooms),
        'avg_temp': round(sum(temps) / len(temps), 1) if temps else None,
        'avg_humidity': round(sum(hums) / len(hums), 1) if hums else None,
    })


@app.route('/records', methods=['POST'])
def create_record():
    data = request.get_json(force=True, silent=True) or {}
    room = (data.get('room') or '').strip()
    if not room:
        return jsonify(error='房间/区域必填'), 400
    r = EnvRecord(
        room=room,
        recorded_at=_parse_dt(data.get('recorded_at')) or datetime.utcnow(),
        temperature=(data.get('temperature') if data.get('temperature') not in (None, '') else None),
        humidity=(data.get('humidity') if data.get('humidity') not in (None, '') else None),
        pm25=(int(data['pm25']) if data.get('pm25') not in (None, '') else None),
        co2=(int(data['co2']) if data.get('co2') not in (None, '') else None),
        notes=(data.get('notes') or '').strip(),
    )
    db.session.add(r)
    db.session.commit()
    return jsonify(_rec_json(r)), 201


@app.route('/records/<int:rid>', methods=['GET'])
def get_record(rid):
    r = EnvRecord.query.get(rid)
    if not r:
        abort(404)
    return jsonify(_rec_json(r))


@app.route('/records/<int:rid>', methods=['PUT'])
def update_record(rid):
    r = EnvRecord.query.get(rid)
    if not r:
        abort(404)
    data = request.get_json(force=True, silent=True) or {}
    if 'room' in data:
        r.room = (data['room'] or '').strip() or r.room
    if 'recorded_at' in data:
        r.recorded_at = _parse_dt(data['recorded_at']) or r.recorded_at
    if 'temperature' in data:
        r.temperature = (data['temperature'] if data['temperature'] not in (None, '') else None)
    if 'humidity' in data:
        r.humidity = (data['humidity'] if data['humidity'] not in (None, '') else None)
    if 'pm25' in data:
        r.pm25 = (int(data['pm25']) if data['pm25'] not in (None, '') else None)
    if 'co2' in data:
        r.co2 = (int(data['co2']) if data['co2'] not in (None, '') else None)
    if 'notes' in data:
        r.notes = (data['notes'] or '').strip()
    db.session.commit()
    return jsonify(_rec_json(r))


@app.route('/records/<int:rid>', methods=['DELETE'])
def delete_record(rid):
    r = EnvRecord.query.get(rid)
    if not r:
        abort(404)
    db.session.delete(r)
    db.session.commit()
    return jsonify(ok=True)


# ───────────────────────── 启动初始化 ─────────────────────────
if HAVE_SQLA:
    with app.app_context():
        db.create_all()
        if EnvRecord.query.count() == 0:
            now = datetime.utcnow()
            samples = [
                ('客厅', now - timedelta(days=2, hours=1), 23.5, 52, 18, 620, '体感舒适'),
                ('主卧', now - timedelta(days=2, hours=1), 22.0, 48, 12, 560, '夜间略低'),
                ('儿童房', now - timedelta(days=1), 24.5, 55, 22, 700, '白天偏高，注意通风'),
                ('客厅', now, 24.0, 50, 15, 600, '空气净化后'),
                ('厨房', now, 26.0, 60, 30, 800, '做饭时湿度上升'),
            ]
            for room, dt, t, h, p, c, nt in samples:
                db.session.add(EnvRecord(room=room, recorded_at=dt, temperature=t,
                                         humidity=h, pm25=p, co2=c, notes=nt))
            db.session.commit()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
