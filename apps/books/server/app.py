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
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///./books.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app) if HAVE_SQLA else None


# ───────────────────────── 数据模型 ─────────────────────────
class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    author = db.Column(db.String(120), default='')
    category = db.Column(db.String(60), default='其他')
    status = db.Column(db.String(20), default='想读')      # 想读/在读/已读
    rating = db.Column(db.Integer, default=0)              # 0~5 星
    publisher = db.Column(db.String(120), default='')
    isbn = db.Column(db.String(40), default='')
    year = db.Column(db.Integer, default=0)                # 出版年份
    borrow_status = db.Column(db.String(20), default='在库')  # 在库/借出（借阅管理）
    publish_date = db.Column(db.String(20), default='')    # 出版日期，如 2014 / 2014-05-01
    notes = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ───────────────────────── 工具 ─────────────────────────
def _clamp_rating(v):
    try:
        v = int(v)
    except Exception:
        v = 0
    return max(0, min(5, v))


def _book_json(b):
    return {
        'id': b.id, 'title': b.title or '', 'author': b.author or '',
        'category': b.category or '其他', 'status': b.status or '想读',
        'rating': b.rating or 0, 'publisher': b.publisher or '',
        'isbn': b.isbn or '', 'year': b.year or 0,
        'borrow_status': b.borrow_status or '在库', 'publish_date': b.publish_date or '',
        'notes': b.notes or '',
        'created_at': b.created_at.isoformat() if b.created_at else None,
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
    return jsonify(ok=True, counts={'books': Book.query.count()} if HAVE_SQLA else {'books': 0})


# ───────────────────────── 藏书管理 ─────────────────────────
@app.route('/books', methods=['GET'])
def list_books():
    q = (request.args.get('q') or '').strip()
    cat = (request.args.get('category') or '').strip()
    st = (request.args.get('status') or '').strip()
    query = Book.query
    if cat:
        query = query.filter_by(category=cat)
    if st:
        query = query.filter_by(status=st)
    if q:
        like = f'%{q}%'
        query = query.filter(db.or_(Book.title.ilike(like), Book.author.ilike(like), Book.isbn.ilike(like)))
    rows = query.order_by(Book.id.desc()).all()
    return jsonify([_book_json(b) for b in rows])


@app.route('/categories', methods=['GET'])
def list_categories():
    from sqlalchemy import func
    rows = db.session.query(Book.category, func.count(Book.id)).group_by(Book.category).all()
    return jsonify([{'category': c, 'count': n} for c, n in rows])


@app.route('/stats', methods=['GET'])
def stats():
    from sqlalchemy import func
    rows = db.session.query(Book.status, func.count(Book.id)).group_by(Book.status).all()
    out = {'想读': 0, '在读': 0, '已读': 0, 'total': Book.query.count()}
    for s, n in rows:
        out[s] = n
    return jsonify(out)


@app.route('/books', methods=['POST'])
def create_book():
    data = request.get_json(force=True, silent=True) or {}
    title = (data.get('title') or '').strip()
    if not title:
        return jsonify(error='书名必填'), 400
    b = Book(
        title=title,
        author=(data.get('author') or '').strip(),
        category=(data.get('category') or '其他').strip() or '其他',
        status=(data.get('status') or '想读').strip() or '想读',
        rating=_clamp_rating(data.get('rating')),
        publisher=(data.get('publisher') or '').strip(),
        isbn=(data.get('isbn') or '').strip(),
        year=int(data.get('year') or 0) or 0,
        borrow_status=(data.get('borrow_status') or '在库').strip() or '在库',
        publish_date=(data.get('publish_date') or '').strip(),
        notes=(data.get('notes') or '').strip(),
    )
    db.session.add(b)
    db.session.commit()
    return jsonify(_book_json(b)), 201


@app.route('/books/<int:bid>', methods=['GET'])
def get_book(bid):
    b = Book.query.get(bid)
    if not b:
        abort(404)
    return jsonify(_book_json(b))


@app.route('/books/<int:bid>', methods=['PUT'])
def update_book(bid):
    b = Book.query.get(bid)
    if not b:
        abort(404)
    data = request.get_json(force=True, silent=True) or {}
    if 'title' in data:
        b.title = (data['title'] or '').strip()
    if 'author' in data:
        b.author = (data['author'] or '').strip()
    if 'category' in data:
        b.category = (data['category'] or '其他').strip() or '其他'
    if 'status' in data:
        b.status = (data['status'] or '想读').strip() or '想读'
    if 'rating' in data:
        b.rating = _clamp_rating(data['rating'])
    if 'publisher' in data:
        b.publisher = (data['publisher'] or '').strip()
    if 'isbn' in data:
        b.isbn = (data['isbn'] or '').strip()
    if 'year' in data:
        b.year = int(data.get('year') or 0) or 0
    if 'borrow_status' in data:
        b.borrow_status = (data['borrow_status'] or '在库').strip() or '在库'
    if 'publish_date' in data:
        b.publish_date = (data['publish_date'] or '').strip()
    if 'notes' in data:
        b.notes = (data['notes'] or '').strip()
    db.session.commit()
    return jsonify(_book_json(b))


@app.route('/books/<int:bid>', methods=['DELETE'])
def delete_book(bid):
    b = Book.query.get(bid)
    if not b:
        abort(404)
    db.session.delete(b)
    db.session.commit()
    return jsonify(ok=True)


# ───────────────────────── 启动初始化 ─────────────────────────
if HAVE_SQLA:
    with app.app_context():
        db.create_all()
        if Book.query.count() == 0:
            samples = [
                ('人类简史', '尤瓦尔·赫拉利', '历史', '已读', 5, '中信出版社', '9787508647357', 2014, '从认知革命到科学革命的宏大叙事。'),
                ('三体', '刘慈欣', '科幻', '在读', 5, '重庆出版社', '9787536692930', 2008, '黑暗森林与宇宙社会学。'),
                ('小狗钱钱', '博多·舍费尔', '理财', '想读', 0, '南海出版公司', '9787544239111', 2009, '给孩子和成人的理财启蒙。'),
            ]
            for t, a, c, s, r, p, i, y, nt in samples:
                db.session.add(Book(title=t, author=a, category=c, status=s, rating=r,
                                    publisher=p, isbn=i, year=y, borrow_status='在库',
                                    publish_date='', notes=nt))
            db.session.commit()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
