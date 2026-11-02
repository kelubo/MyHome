import os
from datetime import datetime, date

from flask import Flask, request, jsonify, abort

try:
    from flask_sqlalchemy import SQLAlchemy
    HAVE_SQLA = True
except Exception:
    HAVE_SQLA = False

app = Flask(__name__)
# 集成模式由 docker-compose 注入 DATABASE_URL（PostgreSQL）；本地缺省回退到 SQLite 文件
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///./subs.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app) if HAVE_SQLA else None


# ───────────────────────── 数据模型 ─────────────────────────
class Subscription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, default='')
    category = db.Column(db.String(40), default='其他')     # 视频/音乐/宽带/保险/教育/其他
    amount = db.Column(db.Float, default=0)                 # 单次金额
    cycle = db.Column(db.String(20), default='月')          # 月/季/年
    next_date = db.Column(db.Date, nullable=True)           # 下次续费/扣费日
    remind_days = db.Column(db.Integer, default=7)          # 提前提醒天数
    notes = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ───────────────────────── 工具 ─────────────────────────
CYCLE_MONTHS = {'月': 1, '季': 3, '年': 12, '周': 0.25}


def _parse_date(s):
    if isinstance(s, date) and not isinstance(s, datetime):
        return s
    if isinstance(s, datetime):
        return s.date()
    try:
        return datetime.strptime(str(s)[:10], '%Y-%m-%d').date()
    except Exception:
        return None


def _days_left(d):
    if not d:
        return None
    return (d - date.today()).days


def _sub_json(s):
    return {
        'id': s.id, 'name': s.name, 'category': s.category or '其他',
        'amount': s.amount or 0, 'cycle': s.cycle or '月',
        'next_date': s.next_date.isoformat() if s.next_date else '',
        'remind_days': s.remind_days or 0,
        'days_left': _days_left(s.next_date),
        'monthly': round((s.amount or 0) / CYCLE_MONTHS.get(s.cycle or '月', 1), 2),
        'notes': s.notes or '',
        'created_at': s.created_at.isoformat() if s.created_at else None,
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
    return jsonify(ok=True, counts={'subs': Subscription.query.count()} if HAVE_SQLA else {'subs': 0})


# ───────────────────────── 订阅管理 ─────────────────────────
@app.route('/subs', methods=['GET'])
def list_subs():
    cat = (request.args.get('category') or '').strip()
    q = Subscription.query
    if cat:
        q = q.filter_by(category=cat)
    rows = q.order_by(Subscription.next_date.asc().nullslast()).all()
    return jsonify([_sub_json(s) for s in rows])


@app.route('/summary', methods=['GET'])
def summary():
    rows = Subscription.query.all()
    monthly = sum(round((s.amount or 0) / CYCLE_MONTHS.get(s.cycle or '月', 1), 2) for s in rows)
    yearly = round(monthly * 12, 2)
    return jsonify({'monthly': round(monthly, 2), 'yearly': yearly, 'count': len(rows)})


@app.route('/subs', methods=['POST'])
def create_sub():
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify(error='名称必填'), 400
    s = Subscription(
        name=name,
        category=(data.get('category') or '其他').strip() or '其他',
        amount=float(data.get('amount') or 0),
        cycle=(data.get('cycle') or '月').strip() or '月',
        next_date=_parse_date(data.get('next_date')),
        remind_days=int(data.get('remind_days') or 7),
        notes=(data.get('notes') or '').strip(),
    )
    db.session.add(s)
    db.session.commit()
    return jsonify(_sub_json(s)), 201


@app.route('/subs/<int:sid>', methods=['GET'])
def get_sub(sid):
    s = Subscription.query.get(sid)
    if not s:
        abort(404)
    return jsonify(_sub_json(s))


@app.route('/subs/<int:sid>', methods=['PUT'])
def update_sub(sid):
    s = Subscription.query.get(sid)
    if not s:
        abort(404)
    data = request.get_json(force=True, silent=True) or {}
    if 'name' in data:
        s.name = (data['name'] or '').strip()
    if 'category' in data:
        s.category = (data['category'] or '其他').strip() or '其他'
    if 'amount' in data:
        s.amount = float(data['amount'] or 0)
    if 'cycle' in data:
        s.cycle = (data['cycle'] or '月').strip() or '月'
    if 'next_date' in data:
        s.next_date = _parse_date(data['next_date'])
    if 'remind_days' in data:
        s.remind_days = int(data['remind_days'] or 0)
    if 'notes' in data:
        s.notes = (data['notes'] or '').strip()
    db.session.commit()
    return jsonify(_sub_json(s))


@app.route('/subs/<int:sid>', methods=['DELETE'])
def delete_sub(sid):
    s = Subscription.query.get(sid)
    if not s:
        abort(404)
    db.session.delete(s)
    db.session.commit()
    return jsonify(ok=True)


# ───────────────────────── 启动初始化 ─────────────────────────
if HAVE_SQLA:
    with app.app_context():
        db.create_all()
        if Subscription.query.count() == 0:
            samples = [
                ('家庭宽带', '宽带', 119, '月', date.today().replace(month=1, day=5), 7, '中国电信 500M，每月 5 号扣费'),
                ('视频会员', '视频', 25, '月', date.today().replace(month=1, day=15), 3, '某视频平台连续包月'),
                ('家庭车险', '保险', 3200, '年', date.today().replace(month=6, day=1), 30, '每年 6 月续保'),
            ]
            for n, c, a, cy, d, rd, nt in samples:
                db.session.add(Subscription(name=n, category=c, amount=a, cycle=cy,
                                           next_date=d, remind_days=rd, notes=nt))
            db.session.commit()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
