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
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///./repair.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app) if HAVE_SQLA else None


# ───────────────────────── 数据模型 ─────────────────────────
class RepairRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)               # 维修项目/标题
    location = db.Column(db.String(120), default='')                # 位置，如 主卧/厨房水管
    category = db.Column(db.String(60), default='其他')             # 水电/电器/墙面/管道/家具/其他
    date = db.Column(db.Date, nullable=True)                        # 维修/发现日期
    cost = db.Column(db.Float, default=0)                           # 费用
    status = db.Column(db.String(20), default='已完成')             # 已完成/进行中/待处理
    next_check = db.Column(db.Date, nullable=True)                  # 下次检查日
    notes = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


CHECK_WARN = 90  # 临近检查阈值（天）


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


def _check_status(next_check, warn=CHECK_WARN):
    if not next_check:
        return 'none', None
    left = (next_check - date.today()).days
    if left < 0:
        return 'overdue', left
    if left <= warn:
        return 'soon', left
    return 'ok', left


def _rep_json(r):
    cstatus, left = _check_status(r.next_check)
    return {
        'id': r.id, 'title': r.title or '', 'location': r.location or '',
        'category': r.category or '其他', 'date': r.date.isoformat() if r.date else '',
        'cost': r.cost or 0, 'status': r.status or '已完成',
        'next_check': r.next_check.isoformat() if r.next_check else '',
        'check_status': cstatus, 'check_days_left': left,
        'notes': r.notes or '', 'created_at': r.created_at.isoformat() if r.created_at else None,
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
    return jsonify(ok=True, counts={'repairs': RepairRecord.query.count()} if HAVE_SQLA else {'repairs': 0})


# ───────────────────────── 维修记录 ─────────────────────────
@app.route('/repairs', methods=['GET'])
def list_repairs():
    q = (request.args.get('q') or '').strip()
    cat = (request.args.get('category') or '').strip()
    status = (request.args.get('status') or '').strip()
    query = RepairRecord.query
    if cat:
        query = query.filter_by(category=cat)
    if status:
        query = query.filter_by(status=status)
    if q:
        like = f'%{q}%'
        query = query.filter(db.or_(RepairRecord.title.ilike(like), RepairRecord.location.ilike(like), RepairRecord.notes.ilike(like)))
    rows = query.order_by(RepairRecord.id.desc()).all()
    return jsonify([_rep_json(r) for r in rows])


@app.route('/categories', methods=['GET'])
def list_categories():
    from sqlalchemy import func
    rows = db.session.query(RepairRecord.category, func.count(RepairRecord.id)).group_by(RepairRecord.category).all()
    return jsonify([{'category': c, 'count': n} for c, n in rows])


@app.route('/stats', methods=['GET'])
def stats():
    rows = RepairRecord.query.all()
    by_status = {'待处理': 0, '进行中': 0, '已完成': 0}
    total_cost = 0.0
    upcoming = 0
    for r in rows:
        if r.status in by_status:
            by_status[r.status] += 1
        if r.cost:
            total_cost += r.cost
        cstatus, left = _check_status(r.next_check)
        if cstatus in ('overdue', 'soon'):
            upcoming += 1
    return jsonify({'total': len(rows), 'by_status': by_status,
                    'total_cost': round(total_cost, 2), 'upcoming_checks': upcoming})


@app.route('/repairs', methods=['POST'])
def create_repair():
    data = request.get_json(force=True, silent=True) or {}
    title = (data.get('title') or '').strip()
    if not title:
        return jsonify(error='标题必填'), 400
    r = RepairRecord(
        title=title,
        location=(data.get('location') or '').strip(),
        category=(data.get('category') or '其他').strip() or '其他',
        date=_parse_date(data.get('date')),
        cost=float(data.get('cost') or 0),
        status=(data.get('status') or '已完成').strip() or '已完成',
        next_check=_parse_date(data.get('next_check')),
        notes=(data.get('notes') or '').strip(),
    )
    db.session.add(r)
    db.session.commit()
    return jsonify(_rep_json(r)), 201


@app.route('/repairs/<int:rid>', methods=['GET'])
def get_repair(rid):
    r = RepairRecord.query.get(rid)
    if not r:
        abort(404)
    return jsonify(_rep_json(r))


@app.route('/repairs/<int:rid>', methods=['PUT'])
def update_repair(rid):
    r = RepairRecord.query.get(rid)
    if not r:
        abort(404)
    data = request.get_json(force=True, silent=True) or {}
    if 'title' in data:
        r.title = (data['title'] or '').strip() or r.title
    if 'location' in data:
        r.location = (data['location'] or '').strip()
    if 'category' in data:
        r.category = (data['category'] or '其他').strip() or '其他'
    if 'date' in data:
        r.date = _parse_date(data['date'])
    if 'cost' in data:
        r.cost = float(data.get('cost') or 0)
    if 'status' in data:
        r.status = (data['status'] or '已完成').strip() or '已完成'
    if 'next_check' in data:
        r.next_check = _parse_date(data['next_check'])
    if 'notes' in data:
        r.notes = (data['notes'] or '').strip()
    db.session.commit()
    return jsonify(_rep_json(r))


@app.route('/repairs/<int:rid>', methods=['DELETE'])
def delete_repair(rid):
    r = RepairRecord.query.get(rid)
    if not r:
        abort(404)
    db.session.delete(r)
    db.session.commit()
    return jsonify(ok=True)


# ───────────────────────── 启动初始化 ─────────────────────────
if HAVE_SQLA:
    with app.app_context():
        db.create_all()
        if RepairRecord.query.count() == 0:
            t = date.today()
            samples = [
                ('更换客厅吸顶灯', '客厅', '电器', t - timedelta(days=30), 120, '已完成', t + timedelta(days=335), 'LED 灯芯老化，已换 new 灯珠。'),
                ('卫生间下水管漏水维修', '主卫', '管道', t - timedelta(days=15), 260, '已完成', t + timedelta(days=350), '密封胶老化，重新打胶。'),
                ('空调滤网清洗', '儿童房', '电器', t - timedelta(days=5), 0, '已完成', t + timedelta(days=85), '示例：下次检查临近，留意提醒。'),
                ('阳台墙面渗水待查', '阳台', '墙面', t - timedelta(days=3), 0, '待处理', None, '雨后墙面有水渍，待约师傅查看。'),
                ('热水器年度安检', '厨房', '水电', t - timedelta(days=60), 80, '已完成', t - timedelta(days=5), '示例：下次检查已逾期，请安排。'),
            ]
            for ti, loc, c, d, co, st, nc, nt in samples:
                db.session.add(RepairRecord(title=ti, location=loc, category=c, date=d,
                                            cost=co, status=st, next_check=nc, notes=nt))
            db.session.commit()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
