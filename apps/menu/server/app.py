import os
from datetime import datetime, date, timedelta

from flask import Flask, request, jsonify, abort

try:
    from flask_sqlalchemy import SQLAlchemy
    HAVE_SQLA = True
except Exception:
    HAVE_SQLA = False

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///./menu.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app) if HAVE_SQLA else None

MEAL_TYPES = ['早餐', '午餐', '晚餐', '加餐']


# ───────────────────────── 数据模型 ─────────────────────────
class MealPlan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)               # 哪一天
    meal_type = db.Column(db.String(20), default='晚餐')     # 早/午/晚/加餐
    recipe_id = db.Column(db.Integer, nullable=True)         # 关联菜谱（可为空，表示自由安排）
    note = db.Column(db.Text, default='')                    # 备注（不含菜谱时填写，如「出去吃」）
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


def _monday(d):
    return d - timedelta(days=d.weekday())


def _plan_json(p):
    return {
        'id': p.id, 'date': p.date.isoformat() if p.date else '',
        'meal_type': p.meal_type or '晚餐', 'recipe_id': p.recipe_id,
        'note': p.note or '', 'created_at': p.created_at.isoformat() if p.created_at else None,
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
    n = MealPlan.query.count() if HAVE_SQLA else 0
    return jsonify(ok=True, counts={'plans': n})


# ───────────────────────── 菜单管理 ─────────────────────────
@app.route('/plans', methods=['GET'])
def list_plans():
    start = request.args.get('start')        # 周一 ISO 日期，返回整周
    end = request.args.get('end')
    q = MealPlan.query
    if start:
        sd = _parse_date(start)
        if sd:
            q = q.filter(MealPlan.date >= sd)
    if end:
        ed = _parse_date(end)
        if ed:
            q = q.filter(MealPlan.date <= ed)
    rows = q.order_by(MealPlan.date.asc(), MealPlan.meal_type.asc()).all()
    return jsonify([_plan_json(p) for p in rows])


@app.route('/plans', methods=['POST'])
def create_plan():
    data = request.get_json(force=True, silent=True) or {}
    d = _parse_date(data.get('date'))
    if not d:
        return jsonify(error='日期必填'), 400
    mt = (data.get('meal_type') or '晚餐').strip() or '晚餐'
    p = MealPlan(
        date=d,
        meal_type=mt,
        recipe_id=int(data['recipe_id']) if data.get('recipe_id') else None,
        note=(data.get('note') or '').strip(),
    )
    db.session.add(p)
    db.session.commit()
    return jsonify(_plan_json(p)), 201


@app.route('/plans/<int:pid>', methods=['PUT'])
def update_plan(pid):
    p = MealPlan.query.get(pid)
    if not p:
        abort(404)
    data = request.get_json(force=True, silent=True) or {}
    if 'date' in data:
        d = _parse_date(data['date'])
        if d:
            p.date = d
    if 'meal_type' in data:
        p.meal_type = (data['meal_type'] or '晚餐').strip() or '晚餐'
    if 'recipe_id' in data:
        p.recipe_id = int(data['recipe_id']) if data.get('recipe_id') else None
    if 'note' in data:
        p.note = (data['note'] or '').strip()
    db.session.commit()
    return jsonify(_plan_json(p))


@app.route('/plans/<int:pid>', methods=['DELETE'])
def delete_plan(pid):
    p = MealPlan.query.get(pid)
    if not p:
        abort(404)
    db.session.delete(p)
    db.session.commit()
    return jsonify(ok=True)


# ───────────────────────── 启动初始化 ─────────────────────────
if HAVE_SQLA:
    with app.app_context():
        db.create_all()
        if MealPlan.query.count() == 0:
            today = date.today()
            mon = _monday(today)
            samples = [
                (mon, '早餐', None, '牛奶 + 面包'),
                (mon, '晚餐', None, '番茄炒蛋（看菜谱）'),
                (mon + timedelta(days=2), '晚餐', None, '可乐鸡翅'),
            ]
            for d, mt, rid, nt in samples:
                db.session.add(MealPlan(date=d, meal_type=mt, recipe_id=rid, note=nt))
            db.session.commit()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
