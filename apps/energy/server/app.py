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
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///./energy.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app) if HAVE_SQLA else None


# ───────────────────────── 数据模型 ─────────────────────────
class UtilityRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    record_date = db.Column(db.Date, nullable=False, default=date.today)  # 抄表/缴费日期
    category = db.Column(db.String(20), nullable=False, default='电')     # 水/电/燃气
    usage = db.Column(db.Float, default=0)                               # 用量
    unit = db.Column(db.String(20), default='')                          # 单位（吨/度/立方米）
    cost = db.Column(db.Float, default=0)                                # 费用
    notes = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


DEFAULT_UNIT = {'水': '吨', '电': '度', '燃气': '立方米'}


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


def _rec_json(r):
    return {
        'id': r.id,
        'record_date': r.record_date.isoformat() if r.record_date else '',
        'category': r.category or '电',
        'usage': r.usage or 0,
        'unit': r.unit or DEFAULT_UNIT.get(r.category or '电', ''),
        'cost': r.cost or 0,
        'notes': r.notes or '',
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
    return jsonify(ok=True, counts={'records': UtilityRecord.query.count()} if HAVE_SQLA else {'records': 0})


# ───────────────────────── 能耗记录 ─────────────────────────
@app.route('/records', methods=['GET'])
def list_records():
    q = (request.args.get('q') or '').strip()
    cat = (request.args.get('category') or '').strip()
    year = (request.args.get('year') or '').strip()
    query = UtilityRecord.query
    if cat:
        query = query.filter_by(category=cat)
    if q:
        like = f'%{q}%'
        query = query.filter(UtilityRecord.notes.ilike(like))
    rows = query.order_by(UtilityRecord.record_date.desc(), UtilityRecord.id.desc()).all()
    if year:
        try:
            y = int(year)
            rows = [r for r in rows if r.record_date and r.record_date.year == y]
        except Exception:
            pass
    return jsonify([_rec_json(r) for r in rows])


@app.route('/categories', methods=['GET'])
def list_categories():
    from sqlalchemy import func
    rows = db.session.query(UtilityRecord.category, func.count(UtilityRecord.id)).group_by(UtilityRecord.category).all()
    return jsonify([{'category': c, 'count': n} for c, n in rows])


@app.route('/years', methods=['GET'])
def list_years():
    rows = UtilityRecord.query.all()
    ys = sorted({r.record_date.year for r in rows if r.record_date}, reverse=True)
    return jsonify(ys)


@app.route('/stats', methods=['GET'])
def stats():
    year = (request.args.get('year') or '').strip()
    rows = UtilityRecord.query.all()
    if year:
        try:
            y = int(year)
            rows = [r for r in rows if r.record_date and r.record_date.year == y]
        except Exception:
            pass
    by_cat = {}
    total_cost = 0.0
    for r in rows:
        c = r.category or '其他'
        d = by_cat.setdefault(c, {'count': 0, 'usage': 0.0, 'cost': 0.0})
        d['count'] += 1
        d['usage'] += (r.usage or 0)
        d['cost'] += (r.cost or 0)
        total_cost += (r.cost or 0)
    for d in by_cat.values():
        d['usage'] = round(d['usage'], 2)
        d['cost'] = round(d['cost'], 2)
    return jsonify({'total': len(rows), 'total_cost': round(total_cost, 2), 'by_category': by_cat})


@app.route('/records', methods=['POST'])
def create_record():
    data = request.get_json(force=True, silent=True) or {}
    category = (data.get('category') or '电').strip() or '电'
    if category not in DEFAULT_UNIT:
        return jsonify(error='类型须为 水/电/燃气'), 400
    rd = _parse_date(data.get('record_date'))
    if not rd:
        return jsonify(error='日期必填'), 400
    r = UtilityRecord(
        record_date=rd,
        category=category,
        usage=float(data.get('usage') or 0),
        unit=(data.get('unit') or '').strip() or DEFAULT_UNIT[category],
        cost=float(data.get('cost') or 0),
        notes=(data.get('notes') or '').strip(),
    )
    db.session.add(r)
    db.session.commit()
    return jsonify(_rec_json(r)), 201


@app.route('/records/<int:rid>', methods=['GET'])
def get_record(rid):
    r = UtilityRecord.query.get(rid)
    if not r:
        abort(404)
    return jsonify(_rec_json(r))


@app.route('/records/<int:rid>', methods=['PUT'])
def update_record(rid):
    r = UtilityRecord.query.get(rid)
    if not r:
        abort(404)
    data = request.get_json(force=True, silent=True) or {}
    if 'category' in data:
        c = (data['category'] or '电').strip() or '电'
        if c not in DEFAULT_UNIT:
            return jsonify(error='类型须为 水/电/燃气'), 400
        r.category = c
    if 'record_date' in data:
        r.record_date = _parse_date(data['record_date']) or r.record_date
    if 'usage' in data:
        r.usage = float(data.get('usage') or 0)
    if 'unit' in data:
        r.unit = (data['unit'] or '').strip() or DEFAULT_UNIT.get(r.category, r.unit)
    if 'cost' in data:
        r.cost = float(data.get('cost') or 0)
    if 'notes' in data:
        r.notes = (data['notes'] or '').strip()
    db.session.commit()
    return jsonify(_rec_json(r))


@app.route('/records/<int:rid>', methods=['DELETE'])
def delete_record(rid):
    r = UtilityRecord.query.get(rid)
    if not r:
        abort(404)
    db.session.delete(r)
    db.session.commit()
    return jsonify(ok=True)


# ───────────────────────── 启动初始化 ─────────────────────────
if HAVE_SQLA:
    with app.app_context():
        db.create_all()
        if UtilityRecord.query.count() == 0:
            t = date.today()
            samples = [
                ('电', t - timedelta(days=60), 320, '度', 180.0, '上月用电'),
                ('水', t - timedelta(days=60), 12, '吨', 48.0, '上月用水'),
                ('燃气', t - timedelta(days=60), 30, '立方米', 90.0, '上月燃气'),
                ('电', t - timedelta(days=30), 350, '度', 196.0, '本月用电偏高'),
                ('水', t - timedelta(days=30), 11, '吨', 44.0, ''),
                ('燃气', t - timedelta(days=30), 28, '立方米', 84.0, ''),
            ]
            for c, d, u, un, co, nt in samples:
                db.session.add(UtilityRecord(record_date=d, category=c, usage=u, unit=un, cost=co, notes=nt))
            db.session.commit()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
