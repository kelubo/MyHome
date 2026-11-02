import os
from datetime import datetime, date

from flask import Flask, request, jsonify, abort

try:
    from flask_sqlalchemy import SQLAlchemy
    HAVE_SQLA = True
except Exception:
    HAVE_SQLA = False

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///./carlog.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app) if HAVE_SQLA else None


# ───────────────────────── 数据模型 ─────────────────────────
class Vehicle(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, default='')     # 车牌 / 名称
    note = db.Column(db.Text, default='')                           # 备注（车型、年份等）
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class MaintenanceRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(db.Integer, nullable=False, index=True)
    date = db.Column(db.Date, nullable=False)                       # 保养日期
    mileage = db.Column(db.Integer, default=0)                      # 当时里程（km）
    item = db.Column(db.String(200), default='')                    # 保养项目
    cost = db.Column(db.Float, default=0)                           # 费用（元）
    next_mileage = db.Column(db.Integer, default=0)                 # 下次保养里程（0=未设）
    next_date = db.Column(db.Date, nullable=True)                   # 下次保养日期
    note = db.Column(db.Text, default='')                           # 备注
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ───────────────────────── 工具 ─────────────────────────
def _parse_date(s):
    if isinstance(s, date) and not isinstance(s, datetime):
        return s
    if isinstance(s, datetime):
        return s.date()
    try:
        return datetime.strptime(str(s)[:10], '%Y-%m-%d').date()
    except Exception:
        return None


def _vehicle_json(v):
    return {'id': v.id, 'name': v.name, 'note': v.note or '',
            'created_at': v.created_at.isoformat() if v.created_at else None}


def _record_json(r):
    return {
        'id': r.id, 'vehicle_id': r.vehicle_id,
        'date': r.date.isoformat() if r.date else '',
        'mileage': r.mileage or 0, 'item': r.item or '', 'cost': r.cost or 0,
        'next_mileage': r.next_mileage or 0,
        'next_date': r.next_date.isoformat() if r.next_date else None,
        'note': r.note or '',
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
    n = MaintenanceRecord.query.count() if HAVE_SQLA else 0
    return jsonify(ok=True, counts={'records': n, 'vehicles': Vehicle.query.count() if HAVE_SQLA else 0})


# ───────────────────────── 车辆 ─────────────────────────
@app.route('/vehicles', methods=['GET'])
def list_vehicles():
    rows = Vehicle.query.order_by(Vehicle.created_at.asc()).all()
    return jsonify([_vehicle_json(v) for v in rows])


@app.route('/vehicles', methods=['POST'])
def create_vehicle():
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify(error='车辆名称必填'), 400
    v = Vehicle(name=name, note=(data.get('note') or '').strip())
    db.session.add(v)
    db.session.commit()
    return jsonify(_vehicle_json(v)), 201


@app.route('/vehicles/<int:vid>', methods=['PUT'])
def update_vehicle(vid):
    v = Vehicle.query.get(vid)
    if not v:
        abort(404)
    data = request.get_json(force=True, silent=True) or {}
    if 'name' in data:
        v.name = (data['name'] or '').strip()
    if 'note' in data:
        v.note = (data['note'] or '').strip()
    db.session.commit()
    return jsonify(_vehicle_json(v))


@app.route('/vehicles/<int:vid>', methods=['DELETE'])
def delete_vehicle(vid):
    v = Vehicle.query.get(vid)
    if not v:
        abort(404)
    for r in MaintenanceRecord.query.filter_by(vehicle_id=vid).all():
        db.session.delete(r)
    db.session.delete(v)
    db.session.commit()
    return jsonify(ok=True)


# ───────────────────────── 保养记录 ─────────────────────────
@app.route('/records', methods=['GET'])
def list_records():
    vid = request.args.get('vehicle_id')
    q = MaintenanceRecord.query
    if vid:
        try:
            q = q.filter_by(vehicle_id=int(vid))
        except Exception:
            pass
    rows = q.order_by(MaintenanceRecord.date.desc()).all()
    return jsonify([_record_json(r) for r in rows])


@app.route('/records', methods=['POST'])
def create_record():
    data = request.get_json(force=True, silent=True) or {}
    vid = data.get('vehicle_id')
    if not vid:
        return jsonify(error='需指定 vehicle_id'), 400
    d = _parse_date(data.get('date'))
    if not d:
        return jsonify(error='保养日期必填'), 400
    item = (data.get('item') or '').strip()
    if not item:
        return jsonify(error='保养项目必填'), 400
    r = MaintenanceRecord(
        vehicle_id=int(vid), date=d,
        mileage=int(data.get('mileage') or 0),
        item=item, cost=float(data.get('cost') or 0),
        next_mileage=int(data.get('next_mileage') or 0),
        next_date=_parse_date(data.get('next_date')) if data.get('next_date') else None,
        note=(data.get('note') or '').strip(),
    )
    db.session.add(r)
    db.session.commit()
    return jsonify(_record_json(r)), 201


@app.route('/records/<int:rid>', methods=['PUT'])
def update_record(rid):
    r = MaintenanceRecord.query.get(rid)
    if not r:
        abort(404)
    data = request.get_json(force=True, silent=True) or {}
    if 'vehicle_id' in data and data['vehicle_id']:
        r.vehicle_id = int(data['vehicle_id'])
    if 'date' in data:
        d = _parse_date(data['date'])
        if d:
            r.date = d
    if 'mileage' in data:
        r.mileage = int(data.get('mileage') or 0)
    if 'item' in data:
        r.item = (data['item'] or '').strip()
    if 'cost' in data:
        r.cost = float(data.get('cost') or 0)
    if 'next_mileage' in data:
        r.next_mileage = int(data.get('next_mileage') or 0)
    if 'next_date' in data:
        r.next_date = _parse_date(data['next_date']) if data['next_date'] else None
    if 'note' in data:
        r.note = (data['note'] or '').strip()
    db.session.commit()
    return jsonify(_record_json(r))


@app.route('/records/<int:rid>', methods=['DELETE'])
def delete_record(rid):
    r = MaintenanceRecord.query.get(rid)
    if not r:
        abort(404)
    db.session.delete(r)
    db.session.commit()
    return jsonify(ok=True)


# ───────────────────────── 启动初始化 ─────────────────────────
if HAVE_SQLA:
    with app.app_context():
        db.create_all()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
