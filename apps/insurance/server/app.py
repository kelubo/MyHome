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
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///./insurance.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app) if HAVE_SQLA else None


# ───────────────────────── 数据模型 ─────────────────────────
class Policy(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)        # 保单名/险种
    category = db.Column(db.String(40), default='其他')     # 车险/医疗险/房屋险/意外险/寿险/其他
    company = db.Column(db.String(120), default='')         # 保险公司
    policy_no = db.Column(db.String(120), default='')       # 保单号
    insured = db.Column(db.String(60), default='')          # 被保人
    premium = db.Column(db.Float, default=0)                # 保费（年）
    coverage = db.Column(db.Float, nullable=True)           # 保额（可空）
    start_date = db.Column(db.Date, nullable=True)          # 生效日
    end_date = db.Column(db.Date, nullable=True)            # 到期日
    remind_days = db.Column(db.Integer, default=30)         # 提前提醒天数
    notes = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


DEFAULT_REMIND = 30


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


def _pol_json(p):
    st, left = _exp_status(p.end_date, p.remind_days)
    return {
        'id': p.id, 'name': p.name or '', 'category': p.category or '其他',
        'company': p.company or '', 'policy_no': p.policy_no or '',
        'insured': p.insured or '', 'premium': p.premium or 0,
        'coverage': p.coverage, 'start_date': p.start_date.isoformat() if p.start_date else '',
        'end_date': p.end_date.isoformat() if p.end_date else '',
        'remind_days': p.remind_days or 0,
        'exp_status': st, 'exp_days_left': left,
        'notes': p.notes or '', 'created_at': p.created_at.isoformat() if p.created_at else None,
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
    return jsonify(ok=True, counts={'policies': Policy.query.count()} if HAVE_SQLA else {'policies': 0})


# ───────────────────────── 保险保单 ─────────────────────────
@app.route('/policies', methods=['GET'])
def list_policies():
    q = (request.args.get('q') or '').strip()
    cat = (request.args.get('category') or '').strip()
    status = (request.args.get('status') or '').strip()
    query = Policy.query
    if cat:
        query = query.filter_by(category=cat)
    if status:
        # 按到期状态筛选：ok/soon/overdue/none
        rows = query.all()
        out = []
        for p in rows:
            st, _ = _exp_status(p.end_date, p.remind_days)
            if st == status:
                out.append(_pol_json(p))
        out.sort(key=lambda x: (x['exp_days_left'] is None, x['exp_days_left'] if x['exp_days_left'] is not None else 1e9))
        return jsonify(out)
    if q:
        like = f'%{q}%'
        query = query.filter(db.or_(Policy.name.ilike(like), Policy.company.ilike(like),
                                    Policy.policy_no.ilike(like), Policy.insured.ilike(like)))
    rows = query.order_by(Policy.id.desc()).all()
    return jsonify([_pol_json(r) for r in rows])


@app.route('/categories', methods=['GET'])
def list_categories():
    from sqlalchemy import func
    rows = db.session.query(Policy.category, func.count(Policy.id)).group_by(Policy.category).all()
    return jsonify([{'category': c, 'count': n} for c, n in rows])


@app.route('/expiring', methods=['GET'])
def expiring():
    rows = Policy.query.all()
    out = []
    for p in rows:
        st, left = _exp_status(p.end_date, p.remind_days)
        if st in ('overdue', 'soon'):
            out.append(_pol_json(p))
    out.sort(key=lambda x: x['exp_days_left'] if x['exp_days_left'] is not None else 1e9)
    return jsonify(out)


@app.route('/stats', methods=['GET'])
def stats():
    rows = Policy.query.all()
    by_cat = {}
    total_premium = 0.0
    expiring = 0
    expired = 0
    for p in rows:
        c = p.category or '其他'
        by_cat[c] = by_cat.get(c, 0) + 1
        total_premium += (p.premium or 0)
        st, _ = _exp_status(p.end_date, p.remind_days)
        if st == 'soon':
            expiring += 1
        elif st == 'overdue':
            expired += 1
    return jsonify({'total': len(rows), 'by_category': by_cat,
                    'total_annual_premium': round(total_premium, 2),
                    'expiring': expiring, 'expired': expired})


@app.route('/policies', methods=['POST'])
def create_policy():
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify(error='保单名必填'), 400
    p = Policy(
        name=name,
        category=(data.get('category') or '其他').strip() or '其他',
        company=(data.get('company') or '').strip(),
        policy_no=(data.get('policy_no') or '').strip(),
        insured=(data.get('insured') or '').strip(),
        premium=float(data.get('premium') or 0),
        coverage=(float(data['coverage']) if data.get('coverage') not in (None, '') else None),
        start_date=_parse_date(data.get('start_date')),
        end_date=_parse_date(data.get('end_date')),
        remind_days=int(data.get('remind_days') or DEFAULT_REMIND),
        notes=(data.get('notes') or '').strip(),
    )
    db.session.add(p)
    db.session.commit()
    return jsonify(_pol_json(p)), 201


@app.route('/policies/<int:pid>', methods=['GET'])
def get_policy(pid):
    p = Policy.query.get(pid)
    if not p:
        abort(404)
    return jsonify(_pol_json(p))


@app.route('/policies/<int:pid>', methods=['PUT'])
def update_policy(pid):
    p = Policy.query.get(pid)
    if not p:
        abort(404)
    data = request.get_json(force=True, silent=True) or {}
    if 'name' in data:
        p.name = (data['name'] or '').strip() or p.name
    if 'category' in data:
        p.category = (data['category'] or '其他').strip() or '其他'
    if 'company' in data:
        p.company = (data['company'] or '').strip()
    if 'policy_no' in data:
        p.policy_no = (data['policy_no'] or '').strip()
    if 'insured' in data:
        p.insured = (data['insured'] or '').strip()
    if 'premium' in data:
        p.premium = float(data.get('premium') or 0)
    if 'coverage' in data:
        p.coverage = (float(data['coverage']) if data['coverage'] not in (None, '') else None)
    if 'start_date' in data:
        p.start_date = _parse_date(data['start_date'])
    if 'end_date' in data:
        p.end_date = _parse_date(data['end_date'])
    if 'remind_days' in data:
        p.remind_days = int(data.get('remind_days') or DEFAULT_REMIND)
    if 'notes' in data:
        p.notes = (data['notes'] or '').strip()
    db.session.commit()
    return jsonify(_pol_json(p))


@app.route('/policies/<int:pid>', methods=['DELETE'])
def delete_policy(pid):
    p = Policy.query.get(pid)
    if not p:
        abort(404)
    db.session.delete(p)
    db.session.commit()
    return jsonify(ok=True)


# ───────────────────────── 启动初始化 ─────────────────────────
if HAVE_SQLA:
    with app.app_context():
        db.create_all()
        if Policy.query.count() == 0:
            t = date.today()
            samples = [
                ('小轿车交强险+商业险', '车险', '人保财险', 'PICC2026-001', '爸爸', 4200, 500000, t - timedelta(days=300), t + timedelta(days=65), 30, '三者 200 万，含车损。'),
                ('全家百万医疗', '医疗险', '平安健康', 'PA-HEA-002', '全家', 2600, 6000000, t - timedelta(days=200), t + timedelta(days=20), 30, '示例：即将到期，请留意续保。'),
                ('住房财产险', '房屋险', '太平洋财险', 'CPIC-HO-003', '家庭', 880, 2000000, t - timedelta(days=400), t - timedelta(days=10), 30, '示例：已过期，请尽快续保。'),
                ('少儿意外险', '意外险', '众安保险', 'ZA-ACC-004', '孩子', 168, 200000, t - timedelta(days=120), t + timedelta(days=240), 30, ''),
            ]
            for nm, c, co, no, ins, pr, cov, sd, ed, rd, nt in samples:
                db.session.add(Policy(name=nm, category=c, company=co, policy_no=no, insured=ins,
                                     premium=pr, coverage=cov, start_date=sd, end_date=ed, remind_days=rd, notes=nt))
            db.session.commit()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
