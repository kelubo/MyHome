import os
from datetime import datetime, date

from flask import Flask, request, jsonify, abort

try:
    from flask_sqlalchemy import SQLAlchemy
    HAVE_SQLA = True
except Exception:
    HAVE_SQLA = False

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///./ledger.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app) if HAVE_SQLA else None


# ───────────────────────── 数据模型 ─────────────────────────
class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)               # 发生日期
    type = db.Column(db.String(10), default='支出')          # 收入 / 支出
    category = db.Column(db.String(40), default='其他')      # 分类（餐饮/居家/教育/工资…）
    account = db.Column(db.String(40), default='')           # 账户（现金/银行卡/微信/支付宝）
    amount = db.Column(db.Float, default=0)                  # 金额
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


def _txn_json(t):
    return {
        'id': t.id, 'date': t.date.isoformat() if t.date else '',
        'type': t.type or '支出', 'category': t.category or '其他',
        'account': t.account or '', 'amount': t.amount or 0,
        'note': t.note or '', 'created_at': t.created_at.isoformat() if t.created_at else None,
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
    n = Transaction.query.count() if HAVE_SQLA else 0
    return jsonify(ok=True, counts={'txns': n})


# ───────────────────────── 账目管理 ─────────────────────────
@app.route('/txns', methods=['GET'])
def list_txns():
    month = (request.args.get('month') or '').strip()        # YYYY-MM
    typ = (request.args.get('type') or '').strip()
    cat = (request.args.get('category') or '').strip()
    q = Transaction.query
    if month:
        q = q.filter(Transaction.date >= month + '-01')
        # 当月最后一天
        y, m = month.split('-')
        if m == '12':
            nxt = date(int(y) + 1, 1, 1)
        else:
            nxt = date(int(y), int(m) + 1, 1)
        q = q.filter(Transaction.date < nxt)
    if typ:
        q = q.filter_by(type=typ)
    if cat:
        q = q.filter_by(category=cat)
    rows = q.order_by(Transaction.date.desc(), Transaction.id.desc()).all()
    return jsonify([_txn_json(t) for t in rows])


@app.route('/summary', methods=['GET'])
def summary():
    month = (request.args.get('month') or '').strip()
    q = Transaction.query
    if month:
        q = q.filter(Transaction.date >= month + '-01')
        y, m = month.split('-')
        nxt = date(int(y), 1, 1) if m == '12' else date(int(y), int(m) + 1, 1)
        q = q.filter(Transaction.date < nxt)
    rows = q.all()
    income = sum(t.amount for t in rows if (t.type or '支出') == '收入')
    expense = sum(t.amount for t in rows if (t.type or '支出') == '支出')
    by_cat = {}
    for t in rows:
        key = t.category or '其他'
        by_cat.setdefault(key, {'income': 0, 'expense': 0})
        if (t.type or '支出') == '收入':
            by_cat[key]['income'] += t.amount
        else:
            by_cat[key]['expense'] += t.amount
    return jsonify({
        'income': round(income, 2), 'expense': round(expense, 2),
        'balance': round(income - expense, 2),
        'by_category': [{'category': k, 'income': round(v['income'], 2),
                         'expense': round(v['expense'], 2)} for k, v in by_cat.items()],
    })


@app.route('/txns', methods=['POST'])
def create_txn():
    data = request.get_json(force=True, silent=True) or {}
    d = _parse_date(data.get('date'))
    if not d:
        return jsonify(error='日期必填'), 400
    amount = float(data.get('amount') or 0)
    if amount <= 0:
        return jsonify(error='金额需大于 0'), 400
    t = Transaction(
        date=d,
        type=(data.get('type') or '支出').strip() or '支出',
        category=(data.get('category') or '其他').strip() or '其他',
        account=(data.get('account') or '').strip(),
        amount=amount,
        note=(data.get('note') or '').strip(),
    )
    db.session.add(t)
    db.session.commit()
    return jsonify(_txn_json(t)), 201


@app.route('/txns/<int:tid>', methods=['PUT'])
def update_txn(tid):
    t = Transaction.query.get(tid)
    if not t:
        abort(404)
    data = request.get_json(force=True, silent=True) or {}
    if 'date' in data:
        d = _parse_date(data['date'])
        if d:
            t.date = d
    if 'type' in data:
        t.type = (data['type'] or '支出').strip() or '支出'
    if 'category' in data:
        t.category = (data['category'] or '其他').strip() or '其他'
    if 'account' in data:
        t.account = (data['account'] or '').strip()
    if 'amount' in data:
        t.amount = float(data['amount'] or 0)
    if 'note' in data:
        t.note = (data['note'] or '').strip()
    db.session.commit()
    return jsonify(_txn_json(t))


@app.route('/txns/<int:tid>', methods=['DELETE'])
def delete_txn(tid):
    t = Transaction.query.get(tid)
    if not t:
        abort(404)
    db.session.delete(t)
    db.session.commit()
    return jsonify(ok=True)


# ───────────────────────── 启动初始化 ─────────────────────────
if HAVE_SQLA:
    with app.app_context():
        db.create_all()
        if Transaction.query.count() == 0:
            today = date.today()
            samples = [
                (today.replace(day=1), '收入', '工资', '银行卡', 12000, '月度工资'),
                (today.replace(day=3), '支出', '居家', '微信', 320, '物业费'),
                (today.replace(day=5), '支出', '餐饮', '支付宝', 86, '超市采购'),
                (today.replace(day=8), '支出', '教育', '微信', 199, '孩子兴趣班'),
            ]
            for d, ty, c, ac, am, nt in samples:
                db.session.add(Transaction(date=d, type=ty, category=c, account=ac,
                                          amount=am, note=nt))
            db.session.commit()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
