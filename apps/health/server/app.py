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
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///./health.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app) if HAVE_SQLA else None


# ───────────────────────── 数据模型 ─────────────────────────
class Record(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    member = db.Column(db.String(60), default='我')          # 家庭成员
    type = db.Column(db.String(40), default='就诊')          # 就诊/用药/体征/疫苗/其他
    date = db.Column(db.Date, nullable=False)
    item = db.Column(db.String(120), default='')             # 项目/诊断/药名
    value = db.Column(db.String(60), default='')             # 数值（体征等）
    unit = db.Column(db.String(20), default='')              # 单位
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
        'id': r.id, 'member': r.member or '我', 'type': r.type or '就诊',
        'date': r.date.isoformat() if r.date else '', 'item': r.item or '',
        'value': r.value or '', 'unit': r.unit or '', 'notes': r.notes or '',
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
    return jsonify(ok=True, counts={'records': Record.query.count()} if HAVE_SQLA else {'records': 0})


# ───────────────────────── 健康记录管理 ─────────────────────────
@app.route('/records', methods=['GET'])
def list_records():
    member = (request.args.get('member') or '').strip()
    rtype = (request.args.get('type') or '').strip()
    q = Record.query
    if member:
        q = q.filter_by(member=member)
    if rtype:
        q = q.filter_by(type=rtype)
    rows = q.order_by(Record.date.desc()).all()
    return jsonify([_rec_json(r) for r in rows])


@app.route('/members', methods=['GET'])
def list_members():
    from sqlalchemy import func
    rows = db.session.query(Record.member, func.count(Record.id)).group_by(Record.member).all()
    return jsonify([{'member': m, 'count': n} for m, n in rows])


@app.route('/records', methods=['POST'])
def create_record():
    data = request.get_json(force=True, silent=True) or {}
    d = _parse_date(data.get('date'))
    if not d:
        return jsonify(error='日期必填'), 400
    r = Record(
        member=(data.get('member') or '我').strip() or '我',
        type=(data.get('type') or '就诊').strip() or '就诊',
        date=d,
        item=(data.get('item') or '').strip(),
        value=(data.get('value') or '').strip(),
        unit=(data.get('unit') or '').strip(),
        notes=(data.get('notes') or '').strip(),
    )
    db.session.add(r)
    db.session.commit()
    return jsonify(_rec_json(r)), 201


@app.route('/records/<int:rid>', methods=['GET'])
def get_record(rid):
    r = Record.query.get(rid)
    if not r:
        abort(404)
    return jsonify(_rec_json(r))


@app.route('/records/<int:rid>', methods=['PUT'])
def update_record(rid):
    r = Record.query.get(rid)
    if not r:
        abort(404)
    data = request.get_json(force=True, silent=True) or {}
    if 'member' in data:
        r.member = (data['member'] or '我').strip() or '我'
    if 'type' in data:
        r.type = (data['type'] or '就诊').strip() or '就诊'
    if 'date' in data:
        d = _parse_date(data['date'])
        if d:
            r.date = d
    if 'item' in data:
        r.item = (data['item'] or '').strip()
    if 'value' in data:
        r.value = (data['value'] or '').strip()
    if 'unit' in data:
        r.unit = (data['unit'] or '').strip()
    if 'notes' in data:
        r.notes = (data['notes'] or '').strip()
    db.session.commit()
    return jsonify(_rec_json(r))


@app.route('/records/<int:rid>', methods=['DELETE'])
def delete_record(rid):
    r = Record.query.get(rid)
    if not r:
        abort(404)
    db.session.delete(r)
    db.session.commit()
    return jsonify(ok=True)


# ───────────────────────── 启动初始化 ─────────────────────────
if HAVE_SQLA:
    with app.app_context():
        db.create_all()
        if Record.query.count() == 0:
            samples = [
                ('我', '就诊', date.today().replace(month=3, day=12), '年度体检', '', '', '各项指标正常'),
                ('我', '体征', date.today().replace(month=3, day=12), '体重', '68.5', 'kg', ''),
                ('孩子', '疫苗', date.today().replace(month=5, day=20), '流感疫苗', '', '', '社区卫生院'),
            ]
            for m, t, d, it, v, u, nt in samples:
                db.session.add(Record(member=m, type=t, date=d, item=it, value=v, unit=u, notes=nt))
            db.session.commit()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
