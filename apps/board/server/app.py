import os
from datetime import datetime

from flask import Flask, request, jsonify, abort

try:
    from flask_sqlalchemy import SQLAlchemy
    HAVE_SQLA = True
except Exception:
    HAVE_SQLA = False

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///./board.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app) if HAVE_SQLA else None


# ───────────────────────── 数据模型 ─────────────────────────
class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), default='')              # 标题（可为空，纯留言）
    content = db.Column(db.Text, nullable=False, default='')   # 内容
    author = db.Column(db.String(60), default='')              # 发布人
    tag = db.Column(db.String(40), default='公告')             # 标签（影响配色）
    pinned = db.Column(db.Boolean, default=False)              # 是否置顶
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ───────────────────────── 工具 ─────────────────────────
def _post_json(p):
    return {
        'id': p.id, 'title': p.title or '', 'content': p.content or '',
        'author': p.author or '', 'tag': p.tag or '公告', 'pinned': bool(p.pinned),
        'created_at': p.created_at.isoformat() if p.created_at else None,
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
    n = Post.query.count() if HAVE_SQLA else 0
    return jsonify(ok=True, counts={'posts': n})


# ───────────────────────── 公告管理 ─────────────────────────
@app.route('/posts', methods=['GET'])
def list_posts():
    rows = Post.query.order_by(Post.pinned.desc(), Post.created_at.desc()).all()
    return jsonify([_post_json(p) for p in rows])


@app.route('/posts', methods=['POST'])
def create_post():
    data = request.get_json(force=True, silent=True) or {}
    content = (data.get('content') or '').strip()
    if not content:
        return jsonify(error='内容必填'), 400
    p = Post(
        title=(data.get('title') or '').strip(),
        content=content,
        author=(data.get('author') or '').strip(),
        tag=(data.get('tag') or '公告').strip() or '公告',
        pinned=bool(data.get('pinned', False)),
    )
    db.session.add(p)
    db.session.commit()
    return jsonify(_post_json(p)), 201


@app.route('/posts/<int:pid>', methods=['PUT'])
def update_post(pid):
    p = Post.query.get(pid)
    if not p:
        abort(404)
    data = request.get_json(force=True, silent=True) or {}
    if 'title' in data:
        p.title = (data['title'] or '').strip()
    if 'content' in data:
        p.content = (data['content'] or '').strip()
    if 'author' in data:
        p.author = (data['author'] or '').strip()
    if 'tag' in data:
        p.tag = (data['tag'] or '公告').strip() or '公告'
    if 'pinned' in data:
        p.pinned = bool(data['pinned'])
    db.session.commit()
    return jsonify(_post_json(p))


@app.route('/posts/<int:pid>', methods=['DELETE'])
def delete_post(pid):
    p = Post.query.get(pid)
    if not p:
        abort(404)
    db.session.delete(p)
    db.session.commit()
    return jsonify(ok=True)


# ───────────────────────── 启动初始化 ─────────────────────────
if HAVE_SQLA:
    with app.app_context():
        db.create_all()
        if Post.query.count() == 0:
            db.session.add(Post(title='欢迎使用家庭公告板', content='在这里发布家庭通知、留言与分工。可置顶、按标签着色。', author='管理员', tag='公告', pinned=True))
            db.session.commit()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
