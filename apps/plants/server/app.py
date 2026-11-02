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
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///./plants.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app) if HAVE_SQLA else None


# ───────────────────────── 数据模型 ─────────────────────────
class Plant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    species = db.Column(db.String(80), default='')            # 品种 / 科属
    location = db.Column(db.String(120), default='')          # 摆放位置
    acquired_date = db.Column(db.Date, nullable=True)         # 入手日期
    water_interval = db.Column(db.Integer, default=7)         # 浇水周期（天）
    fertilize_interval = db.Column(db.Integer, default=30)    # 施肥周期（天）
    last_water = db.Column(db.Date, nullable=True)
    last_fertilize = db.Column(db.Date, nullable=True)
    notes = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class PlantCare(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    plant_id = db.Column(db.Integer, db.ForeignKey('plant.id', ondelete='CASCADE'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    ctype = db.Column(db.String(30), default='其他')          # 浇水/施肥/换盆/修剪/其他
    note = db.Column(db.Text, default='')
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


def _days_since(d):
    if not d:
        return None
    return (date.today() - d).days


def _plant_json(p):
    return {
        'id': p.id, 'name': p.name or '', 'species': p.species or '',
        'location': p.location or '', 'acquired_date': p.acquired_date.isoformat() if p.acquired_date else '',
        'water_interval': p.water_interval or 0, 'fertilize_interval': p.fertilize_interval or 0,
        'last_water': p.last_water.isoformat() if p.last_water else '',
        'last_fertilize': p.last_fertilize.isoformat() if p.last_fertilize else '',
        'notes': p.notes or '',
        'days_since_water': _days_since(p.last_water),
        'days_since_fertilize': _days_since(p.last_fertilize),
        'created_at': p.created_at.isoformat() if p.created_at else None,
    }


def _care_json(c):
    return {
        'id': c.id, 'plant_id': c.plant_id, 'date': c.date.isoformat() if c.date else '',
        'ctype': c.ctype or '其他', 'note': c.note or '',
        'created_at': c.created_at.isoformat() if c.created_at else None,
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
    return jsonify(ok=True, counts={'plants': Plant.query.count()} if HAVE_SQLA else {'plants': 0})


# ───────────────────────── 植物管理 ─────────────────────────
@app.route('/plants', methods=['GET'])
def list_plants():
    rows = Plant.query.order_by(Plant.name).all()
    return jsonify([_plant_json(p) for p in rows])


@app.route('/due', methods=['GET'])
def due():
    rows = Plant.query.all()
    out = []
    for p in rows:
        need_water = bool(p.water_interval and p.last_water and (p.last_water + timedelta(days=p.water_interval)) <= date.today())
        need_fertilize = bool(p.fertilize_interval and p.last_fertilize and (p.last_fertilize + timedelta(days=p.fertilize_interval)) <= date.today())
        if need_water or need_fertilize:
            d = _plant_json(p)
            d['need_water'] = need_water
            d['need_fertilize'] = need_fertilize
            out.append(d)
    return jsonify(out)


@app.route('/plants', methods=['POST'])
def create_plant():
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify(error='植物名称必填'), 400
    p = Plant(
        name=name,
        species=(data.get('species') or '').strip(),
        location=(data.get('location') or '').strip(),
        acquired_date=_parse_date(data.get('acquired_date')),
        water_interval=int(data.get('water_interval') or 7),
        fertilize_interval=int(data.get('fertilize_interval') or 30),
        last_water=_parse_date(data.get('last_water')),
        last_fertilize=_parse_date(data.get('last_fertilize')),
        notes=(data.get('notes') or '').strip(),
    )
    db.session.add(p)
    db.session.commit()
    return jsonify(_plant_json(p)), 201


@app.route('/plants/<int:pid>', methods=['GET'])
def get_plant(pid):
    p = Plant.query.get(pid)
    if not p:
        abort(404)
    return jsonify(_plant_json(p))


@app.route('/plants/<int:pid>', methods=['PUT'])
def update_plant(pid):
    p = Plant.query.get(pid)
    if not p:
        abort(404)
    data = request.get_json(force=True, silent=True) or {}
    if 'name' in data:
        p.name = (data['name'] or '').strip()
    if 'species' in data:
        p.species = (data['species'] or '').strip()
    if 'location' in data:
        p.location = (data['location'] or '').strip()
    if 'acquired_date' in data:
        p.acquired_date = _parse_date(data['acquired_date'])
    if 'water_interval' in data:
        p.water_interval = int(data.get('water_interval') or 0)
    if 'fertilize_interval' in data:
        p.fertilize_interval = int(data.get('fertilize_interval') or 0)
    if 'last_water' in data:
        p.last_water = _parse_date(data['last_water'])
    if 'last_fertilize' in data:
        p.last_fertilize = _parse_date(data['last_fertilize'])
    if 'notes' in data:
        p.notes = (data['notes'] or '').strip()
    db.session.commit()
    return jsonify(_plant_json(p))


@app.route('/plants/<int:pid>', methods=['DELETE'])
def delete_plant(pid):
    p = Plant.query.get(pid)
    if not p:
        abort(404)
    PlantCare.query.filter_by(plant_id=pid).delete()
    db.session.delete(p)
    db.session.commit()
    return jsonify(ok=True)


# ───────────────────────── 养护记录 ─────────────────────────
@app.route('/plants/<int:pid>/care', methods=['GET'])
def list_care(pid):
    rows = PlantCare.query.filter_by(plant_id=pid).order_by(PlantCare.date.desc()).all()
    return jsonify([_care_json(c) for c in rows])


@app.route('/plants/<int:pid>/care', methods=['POST'])
def add_care(pid):
    if not Plant.query.get(pid):
        abort(404)
    data = request.get_json(force=True, silent=True) or {}
    d = _parse_date(data.get('date'))
    if not d:
        return jsonify(error='日期必填'), 400
    c = PlantCare(
        plant_id=pid, date=d,
        ctype=(data.get('ctype') or '其他').strip() or '其他',
        note=(data.get('note') or '').strip(),
    )
    db.session.add(c)
    db.session.commit()
    return jsonify(_care_json(c)), 201


@app.route('/care/<int:cid>', methods=['DELETE'])
def delete_care(cid):
    c = PlantCare.query.get(cid)
    if not c:
        abort(404)
    db.session.delete(c)
    db.session.commit()
    return jsonify(ok=True)


# ───────────────────────── 启动初始化 ─────────────────────────
if HAVE_SQLA:
    with app.app_context():
        db.create_all()
        if Plant.query.count() == 0:
            t = date.today()
            p = Plant(name='绿萝', species='绿萝属 · 喜阴', location='客厅北窗',
                      acquired_date=t.replace(month=t.month-2 or 1), water_interval=5, fertilize_interval=30,
                      last_water=t - timedelta(days=6), last_fertilize=t - timedelta(days=35),
                      notes='好养，见干见湿，避免强光直射。')
            db.session.add(p)
            db.session.commit()
            for ctype, note in [('浇水', '浇透，托盘积水倒掉'), ('施肥', '稀释液肥一次')]:
                db.session.add(PlantCare(plant_id=p.id, date=t - timedelta(days=6 if ctype == '浇水' else 35), ctype=ctype, note=note))
            db.session.commit()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
