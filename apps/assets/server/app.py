import os
from datetime import datetime, date, timedelta

from flask import Flask, request, jsonify, abort

try:
    from flask_sqlalchemy import SQLAlchemy
    HAVE_SQLA = True
except Exception:
    HAVE_SQLA = False

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///./assets.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app) if HAVE_SQLA else None


# ───────────────────────── 数据模型 ─────────────────────────
class Asset(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, default='')
    category = db.Column(db.String(40), default='其他')      # 大家电/数码/家具/厨卫/其他
    location = db.Column(db.String(60), default='')          # 摆放位置（客厅/主卧…）
    purchase_date = db.Column(db.Date, nullable=True)        # 购买日期
    price = db.Column(db.Float, default=0)                   # 购买价格
    warranty_months = db.Column(db.Integer, default=0)       # 保修月数
    warranty_expire = db.Column(db.Date, nullable=True)      # 保修到期（为空则按购买日+月数推算）
    sn = db.Column(db.String(120), default='')              # 序列号 / 型号
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


def _resolve_warranty(data, pd, we):
    """优先用显式到期日；否则按 购买日 + 保修月数 推算。"""
    if we:
        return we
    if pd and (data.get('warranty_months') or 0):
        m = int(data['warranty_months'])
        y, mth = pd.year, pd.month - 1 + m
        while mth > 12:
            mth -= 12
            y += 1
        return date(y, mth, pd.day)
    return None


def _asset_json(a):
    we = a.warranty_expire
    status = 'none'
    days_left = None
    if we:
        days_left = (we - date.today()).days
        if days_left < 0:
            status = 'expired'
        elif days_left <= 90:
            status = 'soon'
        else:
            status = 'ok'
    return {
        'id': a.id, 'name': a.name, 'category': a.category or '其他',
        'location': a.location or '', 'purchase_date': a.purchase_date.isoformat() if a.purchase_date else '',
        'price': a.price or 0, 'warranty_months': a.warranty_months or 0,
        'warranty_expire': we.isoformat() if we else '',
        'warranty_status': status, 'warranty_days_left': days_left,
        'sn': a.sn or '', 'notes': a.notes or '',
        'created_at': a.created_at.isoformat() if a.created_at else None,
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
    n = Asset.query.count() if HAVE_SQLA else 0
    return jsonify(ok=True, counts={'assets': n})


# ───────────────────────── 资产管理 ─────────────────────────
@app.route('/assets', methods=['GET'])
def list_assets():
    cat = (request.args.get('category') or '').strip()
    q = Asset.query
    if cat:
        q = q.filter_by(category=cat)
    rows = q.order_by(Asset.name.asc()).all()
    return jsonify([_asset_json(a) for a in rows])


@app.route('/warranty', methods=['GET'])
def warranty_alerts():
    rows = Asset.query.all()
    out = [a for a in [_asset_json(a) for a in rows]
           if a['warranty_status'] in ('soon', 'expired')]
    out.sort(key=lambda x: (x['warranty_days_left'] if x['warranty_days_left'] is not None else 1e9))
    return jsonify(out)


@app.route('/assets', methods=['POST'])
def create_asset():
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify(error='名称必填'), 400
    pd = _parse_date(data.get('purchase_date'))
    we = _parse_date(data.get('warranty_expire'))
    we = _resolve_warranty(data, pd, we)
    a = Asset(
        name=name,
        category=(data.get('category') or '其他').strip() or '其他',
        location=(data.get('location') or '').strip(),
        purchase_date=pd,
        price=float(data.get('price') or 0),
        warranty_months=int(data.get('warranty_months') or 0),
        warranty_expire=we,
        sn=(data.get('sn') or '').strip(),
        notes=(data.get('notes') or '').strip(),
    )
    db.session.add(a)
    db.session.commit()
    return jsonify(_asset_json(a)), 201


@app.route('/assets/<int:aid>', methods=['PUT'])
def update_asset(aid):
    a = Asset.query.get(aid)
    if not a:
        abort(404)
    data = request.get_json(force=True, silent=True) or {}
    if 'name' in data:
        a.name = (data['name'] or '').strip()
    if 'category' in data:
        a.category = (data['category'] or '其他').strip() or '其他'
    if 'location' in data:
        a.location = (data['location'] or '').strip()
    if 'purchase_date' in data:
        a.purchase_date = _parse_date(data['purchase_date'])
    if 'price' in data:
        a.price = float(data['price'] or 0)
    if 'warranty_months' in data:
        a.warranty_months = int(data['warranty_months'] or 0)
    if 'warranty_expire' in data:
        a.warranty_expire = _parse_date(data['warranty_expire'])
    elif 'purchase_date' in data or 'warranty_months' in data:
        # 重新推算（若未显式给到期日）
        if not a.warranty_expire:
            a.warranty_expire = _resolve_warranty({'warranty_months': a.warranty_months},
                                                 a.purchase_date, None)
    if 'sn' in data:
        a.sn = (data['sn'] or '').strip()
    if 'notes' in data:
        a.notes = (data['notes'] or '').strip()
    db.session.commit()
    return jsonify(_asset_json(a))


@app.route('/assets/<int:aid>', methods=['DELETE'])
def delete_asset(aid):
    a = Asset.query.get(aid)
    if not a:
        abort(404)
    db.session.delete(a)
    db.session.commit()
    return jsonify(ok=True)


# ───────────────────────── 启动初始化 ─────────────────────────
if HAVE_SQLA:
    with app.app_context():
        db.create_all()
        if Asset.query.count() == 0:
            today = date.today()
            samples = [
                ('小米电视', '大家电', '客厅', today.replace(year=today.year - 1), 2999, 12, '', '75 寸 4K'),
                ('海尔冰箱', '大家电', '厨房', today.replace(year=today.year - 2), 4599, 36, '', '双开门'),
                ('戴森吸尘器', '数码', '储物间', today.replace(month=max(1, today.month - 4)), 3290, 24, '', 'V12'),
                ('美的空调', '大家电', '主卧', today.replace(year=today.year - 3), 2899, 60, '', '1.5 匹'),
            ]
            for n, c, loc, pd, pr, wm, sn, nt in samples:
                we = _resolve_warranty({'warranty_months': wm}, pd, None)
                db.session.add(Asset(name=n, category=c, location=loc, purchase_date=pd,
                                    price=pr, warranty_months=wm, warranty_expire=we,
                                    sn=sn, notes=nt))
            db.session.commit()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
