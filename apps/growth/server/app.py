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
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///./growth.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app) if HAVE_SQLA else None


# ───────────────────────── 数据模型 ─────────────────────────
class GrowthRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    child = db.Column(db.String(60), nullable=False, default='宝宝')   # 孩子名字
    date = db.Column(db.Date, nullable=True)                           # 记录日期
    category = db.Column(db.String(40), default='里程碑')              # 身高/体重/疫苗/里程碑/其他
    value = db.Column(db.String(60), default='')                       # 数值，如 85cm / 12.5kg
    title = db.Column(db.String(160), default='')                      # 标题/事件名（里程碑用）
    notes = db.Column(db.Text, default='')
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


def _rec_json(r):
    return {
        'id': r.id, 'child': r.child or '', 'date': r.date.isoformat() if r.date else '',
        'category': r.category or '里程碑', 'value': r.value or '',
        'title': r.title or '', 'notes': r.notes or '',
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
    return jsonify(ok=True, counts={'records': GrowthRecord.query.count()} if HAVE_SQLA else {'records': 0})


# ───────────────────────── 成长记录 ─────────────────────────
@app.route('/records', methods=['GET'])
def list_records():
    q = (request.args.get('q') or '').strip()
    child = (request.args.get('child') or '').strip()
    cat = (request.args.get('category') or '').strip()
    query = GrowthRecord.query
    if child:
        query = query.filter_by(child=child)
    if cat:
        query = query.filter_by(category=cat)
    if q:
        like = f'%{q}%'
        query = query.filter(db.or_(GrowthRecord.title.ilike(like), GrowthRecord.notes.ilike(like), GrowthRecord.value.ilike(like)))
    rows = query.order_by(GrowthRecord.date.desc(), GrowthRecord.id.desc()).all()
    return jsonify([_rec_json(r) for r in rows])


@app.route('/children', methods=['GET'])
def list_children():
    from sqlalchemy import func
    rows = db.session.query(GrowthRecord.child, func.count(GrowthRecord.id)).group_by(GrowthRecord.child).all()
    return jsonify([{'child': c, 'count': n} for c, n in rows])


@app.route('/stats', methods=['GET'])
def stats():
    children = db.session.query(GrowthRecord.child).distinct().all()
    rows = GrowthRecord.query.all()
    by_child = {}
    for r in rows:
        by_child.setdefault(r.child, 0)
        by_child[r.child] += 1
    return jsonify({'total': len(rows), 'children': len(children), 'per_child': by_child})


@app.route('/records', methods=['POST'])
def create_record():
    data = request.get_json(force=True, silent=True) or {}
    child = (data.get('child') or '').strip()
    if not child:
        return jsonify(error='孩子名字必填'), 400
    r = GrowthRecord(
        child=child,
        date=_parse_date(data.get('date')),
        category=(data.get('category') or '里程碑').strip() or '里程碑',
        value=(data.get('value') or '').strip(),
        title=(data.get('title') or '').strip(),
        notes=(data.get('notes') or '').strip(),
    )
    db.session.add(r)
    db.session.commit()
    return jsonify(_rec_json(r)), 201


@app.route('/records/<int:rid>', methods=['GET'])
def get_record(rid):
    r = GrowthRecord.query.get(rid)
    if not r:
        abort(404)
    return jsonify(_rec_json(r))


@app.route('/records/<int:rid>', methods=['PUT'])
def update_record(rid):
    r = GrowthRecord.query.get(rid)
    if not r:
        abort(404)
    data = request.get_json(force=True, silent=True) or {}
    if 'child' in data:
        r.child = (data['child'] or '').strip() or r.child
    if 'date' in data:
        r.date = _parse_date(data['date'])
    if 'category' in data:
        r.category = (data['category'] or '里程碑').strip() or '里程碑'
    if 'value' in data:
        r.value = (data['value'] or '').strip()
    if 'title' in data:
        r.title = (data['title'] or '').strip()
    if 'notes' in data:
        r.notes = (data['notes'] or '').strip()
    db.session.commit()
    return jsonify(_rec_json(r))


@app.route('/records/<int:rid>', methods=['DELETE'])
def delete_record(rid):
    r = GrowthRecord.query.get(rid)
    if not r:
        abort(404)
    db.session.delete(r)
    db.session.commit()
    return jsonify(ok=True)


# ───────────────────────── 启动初始化 ─────────────────────────
if HAVE_SQLA:
    with app.app_context():
        db.create_all()
        if GrowthRecord.query.count() == 0:
            t = date.today()
            samples = [
                ('宝宝', t - timedelta(days=365), '身高', '75cm', '周岁体检', '儿保记录'),
                ('宝宝', t - timedelta(days=365), '体重', '9.8kg', '周岁体检', '儿保记录'),
                ('宝宝', t - timedelta(days=200), '疫苗', '', '麻腮风疫苗', '社区医院接种'),
                ('宝宝', t - timedelta(days=120), '里程碑', '', '第一次独立走路', '扶着沙发走了几步'),
                ('宝宝', t - timedelta(days=30), '里程碑', '', '会叫爸爸妈妈', '清晰叫出'),
                ('宝宝', t - timedelta(days=10), '身高', '85cm', '18月龄体检', '儿保记录'),
            ]
            for ch, d, c, v, ti, nt in samples:
                db.session.add(GrowthRecord(child=ch, date=d, category=c, value=v, title=ti, notes=nt))
            db.session.commit()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
