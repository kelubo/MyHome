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
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///./recipes.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app) if HAVE_SQLA else None


# ───────────────────────── 数据模型 ─────────────────────────
class Recipe(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, default='')
    category = db.Column(db.String(40), default='其他')      # 早餐/午餐/晚餐/汤羹/甜点/其他
    description = db.Column(db.Text, default='')             # 简介
    ingredients = db.Column(db.Text, default='')             # 食材：每行一条「名称 数量 单位」
    steps = db.Column(db.Text, default='')                   # 步骤：每行一步
    servings = db.Column(db.Integer, default=0)              # 份数
    time_min = db.Column(db.Integer, default=0)              # 耗时（分钟）
    notes = db.Column(db.Text, default='')                   # 小贴士
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ───────────────────────── 工具 ─────────────────────────
def _recipe_json(r):
    return {
        'id': r.id, 'name': r.name, 'category': r.category or '其他',
        'description': r.description or '', 'ingredients': r.ingredients or '',
        'steps': r.steps or '', 'servings': r.servings or 0,
        'time_min': r.time_min or 0, 'notes': r.notes or '',
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
    n = Recipe.query.count() if HAVE_SQLA else 0
    return jsonify(ok=True, counts={'recipes': n})


# ───────────────────────── 菜谱管理 ─────────────────────────
@app.route('/recipes', methods=['GET'])
def list_recipes():
    cat = (request.args.get('category') or '').strip()
    q = (request.args.get('q') or '').strip()
    query = Recipe.query
    if cat:
        query = query.filter_by(category=cat)
    if q:
        like = '%' + q + '%'
        query = query.filter(db.or_(Recipe.name.ilike(like),
                                   Recipe.ingredients.ilike(like),
                                   Recipe.description.ilike(like)))
    rows = query.order_by(Recipe.name.asc()).all()
    return jsonify([_recipe_json(r) for r in rows])


@app.route('/categories', methods=['GET'])
def categories():
    rows = db.session.query(Recipe.category, db.func.count(Recipe.id)).group_by(Recipe.category).all()
    return jsonify([{'category': c, 'count': n} for c, n in rows])


@app.route('/recipes', methods=['POST'])
def create_recipe():
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify(error='名称必填'), 400
    r = Recipe(
        name=name,
        category=(data.get('category') or '其他').strip() or '其他',
        description=(data.get('description') or '').strip(),
        ingredients=(data.get('ingredients') or '').strip(),
        steps=(data.get('steps') or '').strip(),
        servings=int(data.get('servings') or 0),
        time_min=int(data.get('time_min') or 0),
        notes=(data.get('notes') or '').strip(),
    )
    db.session.add(r)
    db.session.commit()
    return jsonify(_recipe_json(r)), 201


@app.route('/recipes/<int:rid>', methods=['GET'])
def get_recipe(rid):
    r = Recipe.query.get(rid)
    if not r:
        abort(404)
    return jsonify(_recipe_json(r))


@app.route('/recipes/<int:rid>', methods=['PUT'])
def update_recipe(rid):
    r = Recipe.query.get(rid)
    if not r:
        abort(404)
    data = request.get_json(force=True, silent=True) or {}
    if 'name' in data:
        r.name = (data['name'] or '').strip()
    if 'category' in data:
        r.category = (data['category'] or '其他').strip() or '其他'
    if 'description' in data:
        r.description = (data['description'] or '').strip()
    if 'ingredients' in data:
        r.ingredients = (data['ingredients'] or '').strip()
    if 'steps' in data:
        r.steps = (data['steps'] or '').strip()
    if 'servings' in data:
        r.servings = int(data.get('servings') or 0)
    if 'time_min' in data:
        r.time_min = int(data.get('time_min') or 0)
    if 'notes' in data:
        r.notes = (data['notes'] or '').strip()
    db.session.commit()
    return jsonify(_recipe_json(r))


@app.route('/recipes/<int:rid>', methods=['DELETE'])
def delete_recipe(rid):
    r = Recipe.query.get(rid)
    if not r:
        abort(404)
    db.session.delete(r)
    db.session.commit()
    return jsonify(ok=True)


# ───────────────────────── 启动初始化 ─────────────────────────
if HAVE_SQLA:
    with app.app_context():
        db.create_all()
        if Recipe.query.count() == 0:
            samples = [
                ('番茄炒蛋', '午餐', '家常快手菜，酸甜下饭',
                 '鸡蛋 3 个\n番茄 2 个\n盐 适量\n糖 1 小勺\n油 适量',
                 '鸡蛋打散加少许盐\n番茄切块\n热油先炒蛋盛出\n下番茄炒出汁，加糖\n倒回鸡蛋翻炒均匀',
                 2, 10, '火大快炒更嫩'),
                ('小米粥', '早餐', '养胃暖身',
                 '小米 1 杯\n水 8 杯',
                 '小米淘洗\n加水大火煮开\n转小火熬 30 分钟至稠',
                 3, 35, '可配咸菜'),
                ('可乐鸡翅', '晚餐', '孩子最爱',
                 '鸡翅中 10 个\n可乐 1 罐\n生抽 2 勺\n姜 3 片',
                 '鸡翅划口焯水\n煎至两面金黄\n倒入可乐与生抽\n大火收汁',
                 4, 30, ''),
            ]
            for n, c, d, ing, st, sv, tm, nt in samples:
                db.session.add(Recipe(name=n, category=c, description=d, ingredients=ing,
                                     steps=st, servings=sv, time_min=tm, notes=nt))
            db.session.commit()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
