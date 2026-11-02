import os
import re
from datetime import datetime, date

from flask import Flask, request, jsonify, abort

try:
    from flask_sqlalchemy import SQLAlchemy
    HAVE_SQLA = True
except Exception:
    HAVE_SQLA = False

app = Flask(__name__)
# 集成模式由 docker-compose 注入 DATABASE_URL（PostgreSQL）；本地缺省回退到 SQLite 文件
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///./travel.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app) if HAVE_SQLA else None


# ───────────────────────── 数据模型 ─────────────────────────
class Trip(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    destination = db.Column(db.String(160), default='')
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    budget = db.Column(db.Float, default=0.0)
    currency = db.Column(db.String(10), default='¥')
    notes = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class TripLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(db.Integer, db.ForeignKey('trip.id', ondelete='CASCADE'), nullable=False)
    day = db.Column(db.Date, nullable=True)
    title = db.Column(db.String(160), default='')
    content = db.Column(db.Text, default='')
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


def _trip_json(t):
    return {
        'id': t.id, 'name': t.name or '', 'destination': t.destination or '',
        'start_date': t.start_date.isoformat() if t.start_date else '',
        'end_date': t.end_date.isoformat() if t.end_date else '',
        'budget': t.budget or 0.0, 'currency': t.currency or '¥',
        'notes': t.notes or '',
        'created_at': t.created_at.isoformat() if t.created_at else None,
    }


def _log_json(l):
    return {
        'id': l.id, 'trip_id': l.trip_id, 'day': l.day.isoformat() if l.day else '',
        'title': l.title or '', 'content': l.content or '',
        'created_at': l.created_at.isoformat() if l.created_at else None,
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
    return jsonify(ok=True, counts={'trips': Trip.query.count()} if HAVE_SQLA else {'trips': 0})


# ───────────────────────── 旅行管理 ─────────────────────────
@app.route('/trips', methods=['GET'])
def list_trips():
    rows = Trip.query.order_by(Trip.start_date.is_(None), Trip.start_date.desc()).all()
    return jsonify([_trip_json(t) for t in rows])


@app.route('/stats', methods=['GET'])
def stats():
    today = date.today()
    trips = Trip.query.all()
    upcoming = 0
    ongoing = 0
    for t in trips:
        if t.start_date and t.start_date > today:
            upcoming += 1
        if t.start_date and t.end_date and t.start_date <= today <= t.end_date:
            ongoing += 1
    return jsonify({'total': len(trips), 'upcoming': upcoming, 'ongoing': ongoing})


@app.route('/trips', methods=['POST'])
def create_trip():
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify(error='旅行名称必填'), 400
    t = Trip(
        name=name,
        destination=(data.get('destination') or '').strip(),
        start_date=_parse_date(data.get('start_date')),
        end_date=_parse_date(data.get('end_date')),
        budget=float(data.get('budget') or 0),
        currency=(data.get('currency') or '¥').strip() or '¥',
        notes=(data.get('notes') or '').strip(),
    )
    db.session.add(t)
    db.session.commit()
    return jsonify(_trip_json(t)), 201


@app.route('/trips/<int:tid>', methods=['GET'])
def get_trip(tid):
    t = Trip.query.get(tid)
    if not t:
        abort(404)
    return jsonify(_trip_json(t))


@app.route('/trips/<int:tid>', methods=['PUT'])
def update_trip(tid):
    t = Trip.query.get(tid)
    if not t:
        abort(404)
    data = request.get_json(force=True, silent=True) or {}
    if 'name' in data:
        t.name = (data['name'] or '').strip()
    if 'destination' in data:
        t.destination = (data['destination'] or '').strip()
    if 'start_date' in data:
        t.start_date = _parse_date(data['start_date'])
    if 'end_date' in data:
        t.end_date = _parse_date(data['end_date'])
    if 'budget' in data:
        t.budget = float(data.get('budget') or 0)
    if 'currency' in data:
        t.currency = (data['currency'] or '¥').strip() or '¥'
    if 'notes' in data:
        t.notes = (data['notes'] or '').strip()
    db.session.commit()
    return jsonify(_trip_json(t))


@app.route('/trips/<int:tid>', methods=['DELETE'])
def delete_trip(tid):
    t = Trip.query.get(tid)
    if not t:
        abort(404)
    TripLog.query.filter_by(trip_id=tid).delete()
    db.session.delete(t)
    db.session.commit()
    return jsonify(ok=True)


# ───────────────────────── 游记 / 行程 ─────────────────────────
@app.route('/trips/<int:tid>/logs', methods=['GET'])
def list_logs(tid):
    rows = TripLog.query.filter_by(trip_id=tid).order_by(TripLog.day.is_(None), TripLog.day.asc()).all()
    return jsonify([_log_json(l) for l in rows])


@app.route('/trips/<int:tid>/logs', methods=['POST'])
def add_log(tid):
    if not Trip.query.get(tid):
        abort(404)
    data = request.get_json(force=True, silent=True) or {}
    l = TripLog(
        trip_id=tid,
        day=_parse_date(data.get('day')),
        title=(data.get('title') or '').strip(),
        content=(data.get('content') or '').strip(),
    )
    db.session.add(l)
    db.session.commit()
    return jsonify(_log_json(l)), 201


@app.route('/logs/<int:lid>', methods=['DELETE'])
def delete_log(lid):
    l = TripLog.query.get(lid)
    if not l:
        abort(404)
    db.session.delete(l)
    db.session.commit()
    return jsonify(ok=True)


# ───────────────────────── 旅行足迹地图 ─────────────────────────
class Visit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    province = db.Column(db.String(40), default='')
    city = db.Column(db.String(40), default='')
    district = db.Column(db.String(40), default='')
    town = db.Column(db.String(40), default='')
    arrival = db.Column(db.Date, nullable=True)
    color = db.Column(db.String(20), default='#0ea5e9')
    note = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


def _visit_json(v):
    return {
        'id': v.id, 'province': v.province or '', 'city': v.city or '',
        'district': v.district or '', 'town': v.town or '',
        'arrival': v.arrival.isoformat() if v.arrival else '',
        'color': v.color or '#0ea5e9', 'note': v.note or '',
        'created_at': v.created_at.isoformat() if v.created_at else None,
    }


@app.route('/visits', methods=['GET'])
def list_visits():
    rows = Visit.query.order_by(Visit.arrival.is_(None), Visit.arrival.desc()).all()
    return jsonify([_visit_json(v) for v in rows])


@app.route('/visits', methods=['POST'])
def create_visit():
    data = request.get_json(force=True, silent=True) or {}
    province = (data.get('province') or '').strip()
    if not province:
        return jsonify(error='省份必填'), 400
    v = Visit(
        province=province,
        city=(data.get('city') or '').strip(),
        district=(data.get('district') or '').strip(),
        town=(data.get('town') or '').strip(),
        arrival=_parse_date(data.get('arrival')),
        color=(data.get('color') or '#0ea5e9').strip() or '#0ea5e9',
        note=(data.get('note') or '').strip(),
    )
    db.session.add(v)
    db.session.commit()
    return jsonify(_visit_json(v)), 201


@app.route('/visits/<int:vid>', methods=['PUT'])
def update_visit(vid):
    v = Visit.query.get(vid)
    if not v:
        abort(404)
    data = request.get_json(force=True, silent=True) or {}
    if 'province' in data:
        v.province = (data['province'] or '').strip()
    if 'city' in data:
        v.city = (data['city'] or '').strip()
    if 'district' in data:
        v.district = (data['district'] or '').strip()
    if 'town' in data:
        v.town = (data['town'] or '').strip()
    if 'arrival' in data:
        v.arrival = _parse_date(data['arrival'])
    if 'color' in data:
        v.color = (data['color'] or '#0ea5e9').strip() or '#0ea5e9'
    if 'note' in data:
        v.note = (data['note'] or '').strip()
    db.session.commit()
    return jsonify(_visit_json(v))


@app.route('/visits/<int:vid>', methods=['DELETE'])
def delete_visit(vid):
    v = Visit.query.get(vid)
    if not v:
        abort(404)
    db.session.delete(v)
    db.session.commit()
    return jsonify(ok=True)


@app.route('/visits/export', methods=['GET'])
def export_visits():
    rows = Visit.query.order_by(Visit.arrival.is_(None), Visit.arrival.desc()).all()
    return jsonify([_visit_json(v) for v in rows])


@app.route('/visits/import', methods=['POST'])
def import_visits():
    data = request.get_json(force=True, silent=True) or []
    if not isinstance(data, list):
        return jsonify(error='需为数组'), 400
    added = 0
    for d in data:
        if not (d.get('province') or '').strip():
            continue
        db.session.add(Visit(
            province=(d.get('province') or '').strip(),
            city=(d.get('city') or '').strip(),
            district=(d.get('district') or '').strip(),
            town=(d.get('town') or '').strip(),
            arrival=_parse_date(d.get('arrival')),
            color=(d.get('color') or '#0ea5e9').strip() or '#0ea5e9',
            note=(d.get('note') or '').strip(),
        ))
        added += 1
    db.session.commit()
    return jsonify(ok=True, added=added)


@app.route('/geo/<adcode>')
def geo_proxy(adcode):
    """行政区划 GeoJSON 代理 + 本地缓存（支持省→市→区县级下钻）。

    优先返回本地已缓存文件；未命中则按需从阿里云 DataV 拉取并落盘，
    首次运行需联网，之后全家/各设备访问均走服务器缓存，纯内网可用。
    adcode 为 6 位数字（如 100000 全国、330000 浙江、330100 杭州、330106 西湖区）。
    """
    import json as _json
    import urllib.request
    GEO_DIR = os.environ.get('GEO_DIR', os.path.join(os.path.dirname(__file__), 'geo'))
    if not re.match(r'^\d{6}$', adcode or ''):
        return jsonify(error='invalid adcode'), 400
    path = os.path.join(GEO_DIR, adcode + '_full.json')
    if os.path.exists(path):
        with open(path, 'rb') as f:
            return f.read(), 200, {'Content-Type': 'application/json; charset=utf-8'}
    url = 'https://geo.datav.aliyun.com/areas_v3/bound/' + adcode + '_full.json'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = resp.read()
        _json.loads(data.decode('utf-8'))  # 校验为合法 JSON
        try:
            os.makedirs(GEO_DIR, exist_ok=True)
            with open(path, 'wb') as f:
                f.write(data)
        except Exception:
            pass  # 缓存失败不影响本次返回
        return data, 200, {'Content-Type': 'application/json; charset=utf-8'}
    except Exception as e:
        return jsonify(error='geo fetch failed: ' + str(e)), 502


# ───────────────────────── 启动初始化 ─────────────────────────
if HAVE_SQLA:
    with app.app_context():
        db.create_all()
        if Trip.query.count() == 0:
            t = date.today()
            trip = Trip(name='春节海南行', destination='海南 · 三亚',
                        start_date=t.replace(month=1, day=28), end_date=t.replace(month=2, day=4),
                        budget=12000.0, currency='¥',
                        notes='全家海岛游，提前订好机票酒店。')
            db.session.add(trip)
            db.session.commit()
            logs = [
                (trip.id, t.replace(month=1, day=28), '抵达三亚', '下午航班落地，入住海棠湾酒店，晚上逛了第一市场吃海鲜。'),
                (trip.id, t.replace(month=1, day=30), '蜈支洲岛', '一整天浮潜与沙滩，海水能见度极好，记得涂防晒。'),
            ]
            for tid, d, ti, c in logs:
                db.session.add(TripLog(trip_id=tid, day=d, title=ti, content=c))
            db.session.commit()
            if Visit.query.count() == 0:
                db.session.add(Visit(province='海南省', city='三亚市', arrival=t.replace(month=1, day=28), color='#0ea5e9', note='春节海南行'))
                db.session.add(Visit(province='北京市', city='北京市', arrival=t.replace(month=5, day=1), color='#f59e0b', note='五一北京'))
                db.session.commit()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
