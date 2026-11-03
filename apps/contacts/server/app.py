import os
from datetime import datetime

from flask import Flask, request, jsonify, abort

try:
    from flask_sqlalchemy import SQLAlchemy
    HAVE_SQLA = True
except Exception:
    HAVE_SQLA = False

app = Flask(__name__)
# 集成模式由 docker-compose 注入 DATABASE_URL（PostgreSQL）；本地缺省回退到 SQLite 文件
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///./contacts.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app) if HAVE_SQLA else None


# ───────────────────────── 数据模型 ─────────────────────────
class Contact(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)        # 姓名 / 称呼
    category = db.Column(db.String(40), default='其他')     # 家人/亲友/服务商/紧急联系人/同事/其他
    phone = db.Column(db.String(200), default='')           # 电话（可多个，逗号分隔）
    email = db.Column(db.String(120), default='')
    wechat = db.Column(db.String(60), default='')           # 微信
    address = db.Column(db.String(200), default='')         # 地址
    relation = db.Column(db.String(60), default='')         # 关系 / 角色
    organization = db.Column(db.String(120), default='')    # 单位 / 店铺
    notes = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


DEFAULT = '其他'


# ───────────────────────── 工具 ─────────────────────────
def _json(c):
    return {
        'id': c.id, 'name': c.name or '', 'category': c.category or DEFAULT,
        'phone': c.phone or '', 'email': c.email or '', 'wechat': c.wechat or '',
        'address': c.address or '', 'relation': c.relation or '',
        'organization': c.organization or '', 'notes': c.notes or '',
        'created_at': c.created_at.isoformat() if c.created_at else None,
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
    return jsonify(ok=True, counts={'contacts': Contact.query.count()} if HAVE_SQLA else {'contacts': 0})


# ───────────────────────── 通讯录 ─────────────────────────
@app.route('/contacts', methods=['GET'])
def list_contacts():
    q = (request.args.get('q') or '').strip()
    cat = (request.args.get('category') or '').strip()
    query = Contact.query
    if cat:
        query = query.filter_by(category=cat)
    if q:
        like = f'%{q}%'
        query = query.filter(db.or_(Contact.name.ilike(like), Contact.phone.ilike(like),
                                    Contact.organization.ilike(like), Contact.relation.ilike(like),
                                    Contact.wechat.ilike(like)))
    rows = query.order_by(Contact.id.desc()).all()
    return jsonify([_json(r) for r in rows])


@app.route('/categories', methods=['GET'])
def list_categories():
    from sqlalchemy import func
    rows = db.session.query(Contact.category, func.count(Contact.id)).group_by(Contact.category).all()
    return jsonify([{'category': c, 'count': n} for c, n in rows])


@app.route('/stats', methods=['GET'])
def stats():
    rows = Contact.query.all()
    by_cat = {}
    for c in rows:
        cat = c.category or DEFAULT
        by_cat[cat] = by_cat.get(cat, 0) + 1
    return jsonify({'total': len(rows), 'by_category': by_cat})


@app.route('/contacts', methods=['POST'])
def create_contact():
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify(error='姓名必填'), 400
    c = Contact(
        name=name,
        category=(data.get('category') or DEFAULT).strip() or DEFAULT,
        phone=(data.get('phone') or '').strip(),
        email=(data.get('email') or '').strip(),
        wechat=(data.get('wechat') or '').strip(),
        address=(data.get('address') or '').strip(),
        relation=(data.get('relation') or '').strip(),
        organization=(data.get('organization') or '').strip(),
        notes=(data.get('notes') or '').strip(),
    )
    db.session.add(c)
    db.session.commit()
    return jsonify(_json(c)), 201


@app.route('/contacts/<int:cid>', methods=['GET'])
def get_contact(cid):
    c = Contact.query.get(cid)
    if not c:
        abort(404)
    return jsonify(_json(c))


@app.route('/contacts/<int:cid>', methods=['PUT'])
def update_contact(cid):
    c = Contact.query.get(cid)
    if not c:
        abort(404)
    data = request.get_json(force=True, silent=True) or {}
    for f in ['name', 'category', 'phone', 'email', 'wechat', 'address', 'relation', 'organization', 'notes']:
        if f in data:
            v = (data[f] or '').strip()
            if f == 'name' and not v:
                v = c.name
            if f == 'category' and not v:
                v = DEFAULT
            setattr(c, f, v)
    db.session.commit()
    return jsonify(_json(c))


@app.route('/contacts/<int:cid>', methods=['DELETE'])
def delete_contact(cid):
    c = Contact.query.get(cid)
    if not c:
        abort(404)
    db.session.delete(c)
    db.session.commit()
    return jsonify(ok=True)


# ───────────────────────── 启动初始化 ─────────────────────────
if HAVE_SQLA:
    with app.app_context():
        db.create_all()
        if Contact.query.count() == 0:
            samples = [
                ('爸爸', '家人', '138****0001', '', '', '', '户主', '', '直系家属'),
                ('妈妈', '家人', '138****0002', '', '', '', '', '', '直系家属'),
                ('小区物业', '服务商', '010-12345678', '', '', 'xx小区物业中心', '报修/缴费', '', '工作日 9:00-18:00'),
                ('社区卫生服务中心', '服务商', '139****0003', '', '', 'xx街道社区卫生服务中心', '签约家庭医生', '', '疫苗接种/常见病'),
                ('120 急救', '紧急联系人', '', '', '', '', '突发情况拨打', '', ' emergency'),
            ]
            for nm, cg, ph, em, wx, ad, rl, org, nt in samples:
                db.session.add(Contact(name=nm, category=cg, phone=ph, email=em, wechat=wx,
                                      address=ad, relation=rl, organization=org, notes=nt))
            db.session.commit()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
