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
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///./calendar.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app) if HAVE_SQLA else None


# ───────────────────────── 数据模型 ─────────────────────────
class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False, default='')
    date = db.Column(db.Date, nullable=False)                 # 事件日期（仅日期）
    category = db.Column(db.String(40), default='其他')        # 生日/纪念日/缴费/节日/其他
    notes = db.Column(db.Text, default='')                    # 备注
    repeat = db.Column(db.String(20), default='yearly')       # none/yearly/monthly
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


def _event_json(e):
    return {
        'id': e.id, 'title': e.title, 'date': e.date.isoformat() if e.date else '',
        'category': e.category or '其他', 'notes': e.notes or '', 'repeat': e.repeat or 'yearly',
        'created_at': e.created_at.isoformat() if e.created_at else None,
    }


def _countdown(e, today=None):
    """返回相对今天的天数差：0=今天，正=还有 N 天，负=已过 N 天。"""
    today = today or date.today()
    d = e.date
    if not d:
        return None
    if e.repeat == 'yearly':
        # 取今年或明年的那一天的日期，取更近者
        try:
            this_year = d.replace(year=today.year)
        except Exception:
            this_year = None
        next_year = None
        if this_year and this_year < today:
            try:
                next_year = d.replace(year=today.year + 1)
            except Exception:
                next_year = None
        target = next_year or this_year
        if not target:
            return None
        return (target - today).days
    if e.repeat == 'monthly':
        # 取本月或下月的这一天（无该日则月末）
        def _month_target(month_delta):
            y = today.year + (today.month - 1 + month_delta) // 12
            m = (today.month - 1 + month_delta) % 12 + 1
            day = min(d.day, 28 if m == 2 else 30)
            return date(y, m, day)
        this_month = _month_target(0)
        if this_month < today:
            return (_month_target(1) - today).days
        return (this_month - today).days
    return (d - today).days


# ───────────────────────── 通用 ─────────────────────────
@app.after_request
def _cors(resp):
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Access-Control-Allow-Methods'] = 'GET,POST,PUT,DELETE,OPTIONS'
    resp.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return resp


@app.route('/health')
def health():
    n = Event.query.count() if HAVE_SQLA else 0
    return jsonify(ok=True, counts={'events': n})


# ───────────────────────── 事件管理 ─────────────────────────
@app.route('/events', methods=['GET'])
def list_events():
    cat = (request.args.get('category') or '').strip()
    q = Event.query
    if cat:
        q = q.filter_by(category=cat)
    rows = q.order_by(Event.date.asc()).all()
    return jsonify([_event_json(e) for e in rows])


@app.route('/events', methods=['POST'])
def create_event():
    data = request.get_json(force=True, silent=True) or {}
    title = (data.get('title') or '').strip()
    d = _parse_date(data.get('date'))
    if not title or not d:
        return jsonify(error='标题与日期必填'), 400
    e = Event(title=title, date=d,
              category=(data.get('category') or '其他').strip() or '其他',
              notes=(data.get('notes') or '').strip(),
              repeat=(data.get('repeat') or 'yearly').strip() or 'yearly')
    db.session.add(e)
    db.session.commit()
    return jsonify(_event_json(e)), 201


@app.route('/events/<int:eid>', methods=['GET'])
def get_event(eid):
    e = Event.query.get(eid)
    if not e:
        abort(404)
    return jsonify(_event_json(e))


@app.route('/events/<int:eid>', methods=['PUT'])
def update_event(eid):
    e = Event.query.get(eid)
    if not e:
        abort(404)
    data = request.get_json(force=True, silent=True) or {}
    if 'title' in data:
        e.title = (data['title'] or '').strip()
    if 'date' in data:
        d = _parse_date(data['date'])
        if d:
            e.date = d
    if 'category' in data:
        e.category = (data['category'] or '其他').strip() or '其他'
    if 'notes' in data:
        e.notes = (data['notes'] or '').strip()
    if 'repeat' in data:
        e.repeat = (data['repeat'] or 'yearly').strip() or 'yearly'
    db.session.commit()
    return jsonify(_event_json(e))


@app.route('/events/<int:eid>', methods=['DELETE'])
def delete_event(eid):
    e = Event.query.get(eid)
    if not e:
        abort(404)
    db.session.delete(e)
    db.session.commit()
    return jsonify(ok=True)


@app.route('/upcoming', methods=['GET'])
def upcoming():
    days = request.args.get('days')
    try:
        days = int(days) if days else 60
    except Exception:
        days = 60
    today = date.today()
    rows = Event.query.all()
    out = []
    for e in rows:
        cd = _countdown(e, today)
        if cd is None:
            continue
        if -7 <= cd <= days:        # 已过 7 天内 + 未来 N 天内
            out.append({'event': _event_json(e), 'days': cd})
    out.sort(key=lambda x: x['days'])
    return jsonify(out)


# ───────────────────────── 启动初始化 ─────────────────────────
if HAVE_SQLA:
    with app.app_context():
        db.create_all()

        # 首次启动写入示例数据（仅当库为空）
        if Event.query.count() == 0:
            samples = [
                ('爸爸生日', date.today().replace(month=6, day=15), '生日', '记得订蛋糕', 'yearly'),
                ('结婚纪念日', date.today().replace(month=9, day=9), '纪念日', '提前订餐厅', 'yearly'),
                ('物业费缴纳', date.today().replace(month=12, day=1), '缴费', '每年 12 月缴下一年物业费', 'yearly'),
            ]
            for t, d, c, n, r in samples:
                try:
                    db.session.add(Event(title=t, date=d, category=c, notes=n, repeat=r))
                except Exception:
                    pass
            db.session.commit()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
