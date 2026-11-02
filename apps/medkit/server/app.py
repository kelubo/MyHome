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
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///./medkit.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app) if HAVE_SQLA else None


# ───────────────────────── 数据模型 ─────────────────────────
class Medicine(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(60), default='其他')     # 感冒/退烧/外伤/慢性病/保健/其他
    spec = db.Column(db.String(120), default='')           # 规格，如 0.3g*20粒
    quantity = db.Column(db.Integer, default=0)            # 余量
    unit = db.Column(db.String(20), default='盒')          # 盒/瓶/片/支
    expiry = db.Column(db.Date, nullable=True)             # 有效期
    location = db.Column(db.String(120), default='')       # 存放位置
    usage = db.Column(db.Text, default='')                 # 用法用量 / 用途
    notes = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


EXPIRY_WARN = 90  # 临期阈值（天）


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


def _status_of(expiry, warn=EXPIRY_WARN):
    if not expiry:
        return 'unknown', None
    left = (expiry - date.today()).days
    if left < 0:
        return 'expired', left
    if left <= warn:
        return 'soon', left
    return 'ok', left


def _med_json(m):
    status, left = _status_of(m.expiry)
    return {
        'id': m.id, 'name': m.name or '', 'category': m.category or '其他',
        'spec': m.spec or '', 'quantity': m.quantity or 0, 'unit': m.unit or '盒',
        'expiry': m.expiry.isoformat() if m.expiry else '',
        'location': m.location or '', 'usage': m.usage or '', 'notes': m.notes or '',
        'days_left': left, 'status': status,
        'created_at': m.created_at.isoformat() if m.created_at else None,
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
    return jsonify(ok=True, counts={'medicines': Medicine.query.count()} if HAVE_SQLA else {'medicines': 0})


# ───────────────────────── 药品管理 ─────────────────────────
@app.route('/medicines', methods=['GET'])
def list_meds():
    q = (request.args.get('q') or '').strip()
    cat = (request.args.get('category') or '').strip()
    query = Medicine.query
    if cat:
        query = query.filter_by(category=cat)
    if q:
        like = f'%{q}%'
        query = query.filter(db.or_(Medicine.name.ilike(like), Medicine.usage.ilike(like)))
    rows = query.order_by(Medicine.id.desc()).all()
    return jsonify([_med_json(m) for m in rows])


@app.route('/categories', methods=['GET'])
def list_categories():
    from sqlalchemy import func
    rows = db.session.query(Medicine.category, func.count(Medicine.id)).group_by(Medicine.category).all()
    return jsonify([{'category': c, 'count': n} for c, n in rows])


@app.route('/expiring', methods=['GET'])
def expiring():
    warn = int(request.args.get('days') or EXPIRY_WARN)
    rows = Medicine.query.all()
    out = []
    for m in rows:
        status, left = _status_of(m.expiry, warn)
        if status in ('expired', 'soon'):
            d = _med_json(m)
            out.append(d)
    out.sort(key=lambda x: (x['days_left'] is None, x['days_left'] if x['days_left'] is not None else 0))
    return jsonify(out)


@app.route('/medicines', methods=['POST'])
def create_med():
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify(error='药名必填'), 400
    m = Medicine(
        name=name,
        category=(data.get('category') or '其他').strip() or '其他',
        spec=(data.get('spec') or '').strip(),
        quantity=int(data.get('quantity') or 0),
        unit=(data.get('unit') or '盒').strip() or '盒',
        expiry=_parse_date(data.get('expiry')),
        location=(data.get('location') or '').strip(),
        usage=(data.get('usage') or '').strip(),
        notes=(data.get('notes') or '').strip(),
    )
    db.session.add(m)
    db.session.commit()
    return jsonify(_med_json(m)), 201


@app.route('/medicines/<int:mid>', methods=['GET'])
def get_med(mid):
    m = Medicine.query.get(mid)
    if not m:
        abort(404)
    return jsonify(_med_json(m))


@app.route('/medicines/<int:mid>', methods=['PUT'])
def update_med(mid):
    m = Medicine.query.get(mid)
    if not m:
        abort(404)
    data = request.get_json(force=True, silent=True) or {}
    if 'name' in data:
        m.name = (data['name'] or '').strip()
    if 'category' in data:
        m.category = (data['category'] or '其他').strip() or '其他'
    if 'spec' in data:
        m.spec = (data['spec'] or '').strip()
    if 'quantity' in data:
        m.quantity = int(data.get('quantity') or 0)
    if 'unit' in data:
        m.unit = (data['unit'] or '盒').strip() or '盒'
    if 'expiry' in data:
        m.expiry = _parse_date(data['expiry'])
    if 'location' in data:
        m.location = (data['location'] or '').strip()
    if 'usage' in data:
        m.usage = (data['usage'] or '').strip()
    if 'notes' in data:
        m.notes = (data['notes'] or '').strip()
    db.session.commit()
    return jsonify(_med_json(m))


@app.route('/medicines/<int:mid>', methods=['DELETE'])
def delete_med(mid):
    m = Medicine.query.get(mid)
    if not m:
        abort(404)
    db.session.delete(m)
    db.session.commit()
    return jsonify(ok=True)


# ───────────────────────── 启动初始化 ─────────────────────────
if HAVE_SQLA:
    with app.app_context():
        db.create_all()
        if Medicine.query.count() == 0:
            t = date.today()
            samples = [
                ('布洛芬缓释胶囊', '退烧', '0.3g*20粒', 1, '盒', t + timedelta(days=200), '客厅药箱', '发热、牙痛', '饭后服用，避免空腹。'),
                ('创可贴', '外伤', '100片/盒', 3, '盒', t + timedelta(days=400), '玄关抽屉', '小伤口止血保护', '保持伤口清洁再贴。'),
                ('氯雷他定片', '过敏', '10mg*6片', 2, '盒', t - timedelta(days=10), '卧室床头', '过敏性鼻炎缓解', '示例：已过期，请核对后处理。'),
            ]
            for n, c, sp, q, u, e, loc, us, nt in samples:
                db.session.add(Medicine(name=n, category=c, spec=sp, quantity=q, unit=u,
                                        expiry=e, location=loc, usage=us, notes=nt))
            db.session.commit()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
