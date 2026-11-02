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
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///./tasks.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app) if HAVE_SQLA else None


# ───────────────────────── 数据模型 ─────────────────────────
class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False, default='')
    assignee = db.Column(db.String(60), default='')          # 负责人
    status = db.Column(db.String(20), default='todo')        # todo/doing/done
    priority = db.Column(db.String(10), default='中')        # 高/中/低
    due_date = db.Column(db.Date, nullable=True)
    notes = db.Column(db.Text, default='')
    sort_order = db.Column(db.Integer, default=0)
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


def _task_json(t):
    return {
        'id': t.id, 'title': t.title, 'assignee': t.assignee or '',
        'status': t.status or 'todo', 'priority': t.priority or '中',
        'due_date': t.due_date.isoformat() if t.due_date else '',
        'notes': t.notes or '', 'sort_order': t.sort_order or 0,
        'created_at': t.created_at.isoformat() if t.created_at else None,
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
    return jsonify(ok=True, counts={'tasks': Task.query.count()} if HAVE_SQLA else {'tasks': 0})


# ───────────────────────── 任务管理 ─────────────────────────
@app.route('/tasks', methods=['GET'])
def list_tasks():
    rows = Task.query.order_by(Task.sort_order.asc(), Task.created_at.desc()).all()
    return jsonify([_task_json(t) for t in rows])


@app.route('/tasks', methods=['POST'])
def create_task():
    data = request.get_json(force=True, silent=True) or {}
    title = (data.get('title') or '').strip()
    if not title:
        return jsonify(error='标题必填'), 400
    max_order = db.session.query(db.func.max(Task.sort_order)).scalar() or 0
    t = Task(
        title=title,
        assignee=(data.get('assignee') or '').strip(),
        status=(data.get('status') or 'todo').strip() or 'todo',
        priority=(data.get('priority') or '中').strip() or '中',
        due_date=_parse_date(data.get('due_date')),
        notes=(data.get('notes') or '').strip(),
        sort_order=max_order + 1,
    )
    db.session.add(t)
    db.session.commit()
    return jsonify(_task_json(t)), 201


@app.route('/tasks/<int:tid>', methods=['GET'])
def get_task(tid):
    t = Task.query.get(tid)
    if not t:
        abort(404)
    return jsonify(_task_json(t))


@app.route('/tasks/<int:tid>', methods=['PUT'])
def update_task(tid):
    t = Task.query.get(tid)
    if not t:
        abort(404)
    data = request.get_json(force=True, silent=True) or {}
    if 'title' in data:
        t.title = (data['title'] or '').strip()
    if 'assignee' in data:
        t.assignee = (data['assignee'] or '').strip()
    if 'status' in data:
        t.status = (data['status'] or 'todo').strip() or 'todo'
    if 'priority' in data:
        t.priority = (data['priority'] or '中').strip() or '中'
    if 'due_date' in data:
        t.due_date = _parse_date(data['due_date'])
    if 'notes' in data:
        t.notes = (data['notes'] or '').strip()
    db.session.commit()
    return jsonify(_task_json(t))


@app.route('/tasks/<int:tid>', methods=['DELETE'])
def delete_task(tid):
    t = Task.query.get(tid)
    if not t:
        abort(404)
    db.session.delete(t)
    db.session.commit()
    return jsonify(ok=True)


# ───────────────────────── 启动初始化 ─────────────────────────
if HAVE_SQLA:
    with app.app_context():
        db.create_all()
        if Task.query.count() == 0:
            samples = [
                ('缴这个月水电费', '爸爸', 'todo', '高', date.today().replace(day=20), '记得用app缴'),
                ('周末大扫除', '妈妈', 'todo', '中', None, '客厅+厨房'),
                ('带小狗打疫苗', '孩子', 'doing', '中', date.today().replace(day=25), '约了宠物医院'),
                ('采购下周食材', '妈妈', 'done', '低', None, '已完成'),
            ]
            order = 1
            for ti, who, st, pr, du, nt in samples:
                db.session.add(Task(title=ti, assignee=who, status=st, priority=pr,
                                   due_date=du, notes=nt, sort_order=order))
                order += 1
            db.session.commit()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
