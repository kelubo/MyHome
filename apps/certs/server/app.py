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
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///./certs.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app) if HAVE_SQLA else None


# ───────────────────────── 数据模型 ─────────────────────────
class Certificate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)        # 证件名称
    category = db.Column(db.String(40), default='其他')     # 身份证/护照/户口本/房产证/驾照/结婚证/营业执照/其他
    holder = db.Column(db.String(60), default='')           # 持有人
    number = db.Column(db.String(120), default='')          # 证件号
    issuer = db.Column(db.String(120), default='')          # 签发机关
    issue_date = db.Column(db.Date, nullable=True)          # 签发日
    expire_date = db.Column(db.Date, nullable=True)         # 到期日（长期证件留空）
    remind_days = db.Column(db.Integer, default=90)         # 提前提醒天数
    notes = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


DEFAULT_REMIND = 90


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


def _exp_status(end, remind):
    if not end:
        return 'none', None
    left = (end - date.today()).days
    if left < 0:
        return 'overdue', left
    if left <= (remind or DEFAULT_REMIND):
        return 'soon', left
    return 'ok', left


def _cert_json(c):
    st, left = _exp_status(c.expire_date, c.remind_days)
    return {
        'id': c.id, 'name': c.name or '', 'category': c.category or '其他',
        'holder': c.holder or '', 'number': c.number or '',
        'issuer': c.issuer or '', 'issue_date': c.issue_date.isoformat() if c.issue_date else '',
        'expire_date': c.expire_date.isoformat() if c.expire_date else '',
        'remind_days': c.remind_days or 0,
        'exp_status': st, 'exp_days_left': left,
        'notes': c.notes or '', 'created_at': c.created_at.isoformat() if c.created_at else None,
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
    return jsonify(ok=True, counts={'certs': Certificate.query.count()} if HAVE_SQLA else {'certs': 0})


# ───────────────────────── 证件档案 ─────────────────────────
@app.route('/certs', methods=['GET'])
def list_certs():
    q = (request.args.get('q') or '').strip()
    cat = (request.args.get('category') or '').strip()
    status = (request.args.get('status') or '').strip()
    query = Certificate.query
    if cat:
        query = query.filter_by(category=cat)
    if status:
        rows = query.all()
        out = []
        for c in rows:
            st, _ = _exp_status(c.expire_date, c.remind_days)
            if st == status:
                out.append(_cert_json(c))
        out.sort(key=lambda x: (x['exp_days_left'] is None, x['exp_days_left'] if x['exp_days_left'] is not None else 1e9))
        return jsonify(out)
    if q:
        like = f'%{q}%'
        query = query.filter(db.or_(Certificate.name.ilike(like), Certificate.holder.ilike(like),
                                    Certificate.number.ilike(like), Certificate.issuer.ilike(like)))
    rows = query.order_by(Certificate.id.desc()).all()
    return jsonify([_cert_json(r) for r in rows])


@app.route('/categories', methods=['GET'])
def list_categories():
    from sqlalchemy import func
    rows = db.session.query(Certificate.category, func.count(Certificate.id)).group_by(Certificate.category).all()
    return jsonify([{'category': c, 'count': n} for c, n in rows])


@app.route('/expiring', methods=['GET'])
def expiring():
    rows = Certificate.query.all()
    out = []
    for c in rows:
        st, left = _exp_status(c.expire_date, c.remind_days)
        if st in ('overdue', 'soon'):
            out.append(_cert_json(c))
    out.sort(key=lambda x: x['exp_days_left'] if x['exp_days_left'] is not None else 1e9)
    return jsonify(out)


@app.route('/stats', methods=['GET'])
def stats():
    rows = Certificate.query.all()
    by_cat = {}
    expiring = 0
    expired = 0
    for c in rows:
        cat = c.category or '其他'
        by_cat[cat] = by_cat.get(cat, 0) + 1
        st, _ = _exp_status(c.expire_date, c.remind_days)
        if st == 'soon':
            expiring += 1
        elif st == 'overdue':
            expired += 1
    return jsonify({'total': len(rows), 'by_category': by_cat, 'expiring': expiring, 'expired': expired})


@app.route('/certs', methods=['POST'])
def create_cert():
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify(error='证件名称必填'), 400
    c = Certificate(
        name=name,
        category=(data.get('category') or '其他').strip() or '其他',
        holder=(data.get('holder') or '').strip(),
        number=(data.get('number') or '').strip(),
        issuer=(data.get('issuer') or '').strip(),
        issue_date=_parse_date(data.get('issue_date')),
        expire_date=_parse_date(data.get('expire_date')),
        remind_days=int(data.get('remind_days') or DEFAULT_REMIND),
        notes=(data.get('notes') or '').strip(),
    )
    db.session.add(c)
    db.session.commit()
    return jsonify(_cert_json(c)), 201


@app.route('/certs/<int:cid>', methods=['GET'])
def get_cert(cid):
    c = Certificate.query.get(cid)
    if not c:
        abort(404)
    return jsonify(_cert_json(c))


@app.route('/certs/<int:cid>', methods=['PUT'])
def update_cert(cid):
    c = Certificate.query.get(cid)
    if not c:
        abort(404)
    data = request.get_json(force=True, silent=True) or {}
    if 'name' in data:
        c.name = (data['name'] or '').strip() or c.name
    if 'category' in data:
        c.category = (data['category'] or '其他').strip() or '其他'
    if 'holder' in data:
        c.holder = (data['holder'] or '').strip()
    if 'number' in data:
        c.number = (data['number'] or '').strip()
    if 'issuer' in data:
        c.issuer = (data['issuer'] or '').strip()
    if 'issue_date' in data:
        c.issue_date = _parse_date(data['issue_date'])
    if 'expire_date' in data:
        c.expire_date = _parse_date(data['expire_date'])
    if 'remind_days' in data:
        c.remind_days = int(data.get('remind_days') or DEFAULT_REMIND)
    if 'notes' in data:
        c.notes = (data['notes'] or '').strip()
    db.session.commit()
    return jsonify(_cert_json(c))


@app.route('/certs/<int:cid>', methods=['DELETE'])
def delete_cert(cid):
    c = Certificate.query.get(cid)
    if not c:
        abort(404)
    db.session.delete(c)
    db.session.commit()
    return jsonify(ok=True)


# ───────────────────────── 启动初始化 ─────────────────────────
if HAVE_SQLA:
    with app.app_context():
        db.create_all()
        if Certificate.query.count() == 0:
            t = date.today()
            samples = [
                ('居民身份证', '身份证', '爸爸', '110101********1234', '公安分局', t - timedelta(days=2000), t + timedelta(days=4000), 90, '长期（示例到期日仅作演示）。'),
                ('中华人民共和国护照', '护照', '妈妈', 'E12345678', '出入境管理局', t - timedelta(days=800), t + timedelta(days=60), 90, '示例：即将到期，请留意换发。'),
                ('不动产权证书', '房产证', '家庭', '京(2020)不动产权第0001号', '不动产登记中心', t - timedelta(days=2200), None, 90, '长期有效。'),
                ('机动车驾驶证', '驾照', '爸爸', '110101********5678', '公安交管', t - timedelta(days=1200), t - timedelta(days=15), 90, '示例：已过期，需换证。'),
            ]
            for nm, cg, hd, no, iss, idt, edt, rd, nt in samples:
                db.session.add(Certificate(name=nm, category=cg, holder=hd, number=no, issuer=iss,
                                          issue_date=idt, expire_date=edt, remind_days=rd, notes=nt))
            db.session.commit()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
