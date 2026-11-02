import os
from datetime import datetime, date

from flask import Flask, request, jsonify, abort

try:
    from flask_sqlalchemy import SQLAlchemy
    HAVE_SQLA = True
except Exception:
    HAVE_SQLA = False

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///./pantry.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app) if HAVE_SQLA else None


# ───────────────────────── 数据模型 ─────────────────────────
class Item(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, default='')
    category = db.Column(db.String(40), default='其他')       # 分类（食材/日用品/其他）
    location = db.Column(db.String(20), default='shopping')  # shopping=购物清单 fridge=冰箱库存
    quantity = db.Column(db.Float, default=1)                # 数量
    unit = db.Column(db.String(20), default='')              # 单位（个/瓶/袋…）
    expiry = db.Column(db.Date, nullable=True)               # 保质期（冰箱库存用，可为空）
    checked = db.Column(db.Boolean, default=False)           # 购物清单：是否已购买
    note = db.Column(db.Text, default='')
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


def _item_json(it):
    return {
        'id': it.id, 'name': it.name, 'category': it.category or '其他',
        'location': it.location or 'shopping', 'quantity': it.quantity or 1,
        'unit': it.unit or '', 'expiry': it.expiry.isoformat() if it.expiry else None,
        'checked': bool(it.checked), 'note': it.note or '',
        'created_at': it.created_at.isoformat() if it.created_at else None,
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
    n = Item.query.count() if HAVE_SQLA else 0
    return jsonify(ok=True, counts={'items': n})


# ───────────────────────── 物品管理 ─────────────────────────
@app.route('/items', methods=['GET'])
def list_items():
    loc = (request.args.get('location') or '').strip()
    cat = (request.args.get('category') or '').strip()
    q = Item.query
    if loc:
        q = q.filter_by(location=loc)
    if cat:
        q = q.filter_by(category=cat)
    rows = q.order_by(Item.created_at.desc()).all()
    return jsonify([_item_json(it) for it in rows])


@app.route('/items', methods=['POST'])
def create_item():
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify(error='名称必填'), 400
    try:
        qty = float(data.get('quantity') or 1)
    except Exception:
        qty = 1
    it = Item(
        name=name,
        category=(data.get('category') or '其他').strip() or '其他',
        location=(data.get('location') or 'shopping').strip() or 'shopping',
        quantity=qty,
        unit=(data.get('unit') or '').strip(),
        expiry=_parse_date(data.get('expiry')) if data.get('expiry') else None,
        checked=bool(data.get('checked', False)),
        note=(data.get('note') or '').strip(),
    )
    db.session.add(it)
    db.session.commit()
    return jsonify(_item_json(it)), 201


@app.route('/items/<int:iid>', methods=['PUT'])
def update_item(iid):
    it = Item.query.get(iid)
    if not it:
        abort(404)
    data = request.get_json(force=True, silent=True) or {}
    if 'name' in data:
        it.name = (data['name'] or '').strip()
    if 'category' in data:
        it.category = (data['category'] or '其他').strip() or '其他'
    if 'location' in data:
        it.location = (data['location'] or 'shopping').strip() or 'shopping'
    if 'quantity' in data:
        try:
            it.quantity = float(data['quantity'])
        except Exception:
            pass
    if 'unit' in data:
        it.unit = (data['unit'] or '').strip()
    if 'expiry' in data:
        it.expiry = _parse_date(data['expiry']) if data['expiry'] else None
    if 'checked' in data:
        it.checked = bool(data['checked'])
    if 'note' in data:
        it.note = (data['note'] or '').strip()
    db.session.commit()
    return jsonify(_item_json(it))


@app.route('/items/<int:iid>', methods=['DELETE'])
def delete_item(iid):
    it = Item.query.get(iid)
    if not it:
        abort(404)
    db.session.delete(it)
    db.session.commit()
    return jsonify(ok=True)


# ───────────────────────── 启动初始化 ─────────────────────────
if HAVE_SQLA:
    with app.app_context():
        db.create_all()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
