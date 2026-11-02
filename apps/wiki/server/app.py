import os
import re
import mimetypes
import secrets
from datetime import datetime

from flask import Flask, request, jsonify, abort, send_file

try:
    from flask_sqlalchemy import SQLAlchemy
    HAVE_SQLA = True
except Exception:
    HAVE_SQLA = False

app = Flask(__name__)
# 集成模式由 docker-compose 注入 DATABASE_URL（PostgreSQL）；本地缺省回退到 SQLite 文件
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///./wiki.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = int(os.environ.get('WIKI_MAX_UPLOAD', 50 * 1024 * 1024))  # 单文件上限 50MB
# 附件存储目录（容器内路径；docker-compose 已把 ./data/wiki 挂到这里）
ATTACH_DIR = os.environ.get('WIKI_DATA_DIR', '/data/wiki/attachments')
db = SQLAlchemy(app) if HAVE_SQLA else None


# ───────────────────────── 数据模型 ─────────────────────────
class Page(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False, default='未命名')
    category = db.Column(db.String(60), default='未分类')
    tags = db.Column(db.Text, default='')            # 逗号分隔
    content = db.Column(db.Text, default='')         # Markdown 原文
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)


class Attachment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    page_id = db.Column(db.Integer, nullable=False, index=True)
    filename = db.Column(db.String(255), nullable=False)   # 存储名（随机化，防冲突/穿越）
    original = db.Column(db.String(300), default='')       # 原始文件名（展示用）
    mime = db.Column(db.String(120), default='')
    size = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# 首次启动的种子页（仅当库为空时写入），帮助直观看到排版效果
SEED_TITLE = '欢迎使用家用手册'
SEED_CATEGORY = '说明'
SEED_CONTENT = '''# 家用手册 · 家里的大小事都记这里

这是一个**纯文本 Markdown** 知识库，专门存放家里常用、又怕忘记的信息：WiFi 密码、家电说明书、保修期、物业/水电联系方式等。

## 能写什么

- 标题、列表、**加粗**、*斜体*、`行内代码` 都支持
- 链接：[MyHome 门户](/)  （站内相对链接也可）
- 图片：![示意图](/apps/home/assets/topology.jpg)
- 引用：
  > 重要的事情说三遍
- 代码块：

```text
宽带账号：xxxx
宽带密码：xxxx
```

## 示例：家庭网络

| 项目 | 内容 |
| --- | --- |
| 宽带运营商 | 中国电信 |
| 光猫 IP | 192.168.1.1 |
| WiFi 名称 | MyHome-5G |
| WiFi 密码 | 见下方「网络账号」页 |

> 提示：左侧可搜索、按分类筛选；右上角「＋ 新建」添加新页；编辑时右侧实时预览。
'''


# ───────────────────────── 工具 ─────────────────────────
def _excerpt(text, n=120):
    t = re.sub(r'\s+', ' ', (text or '')).strip()
    return t[:n] + ('…' if len(t) > n else '')


def _page_summary(p):
    return {
        'id': p.id,
        'title': p.title,
        'category': p.category,
        'tags': p.tags or '',
        'updated_at': p.updated_at.isoformat() if p.updated_at else None,
        'excerpt': _excerpt(p.content),
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
    return jsonify(ok=True, counts={'pages': Page.query.count()} if HAVE_SQLA else {'pages': 0})


# ───────────────────────── 页面列表 / 搜索 / 分类筛选 ─────────────────────────
@app.route('/pages', methods=['GET'])
def list_pages():
    q = (request.args.get('q') or '').strip()
    cat = (request.args.get('category') or '').strip()
    query = Page.query
    if cat:
        query = query.filter(Page.category == cat)
    if q:
        like = '%' + q + '%'
        query = query.filter(db.or_(
            Page.title.ilike(like),
            Page.content.ilike(like),
            Page.tags.ilike(like),
            Page.category.ilike(like),
        ))
    rows = query.order_by(Page.updated_at.desc()).all()
    return jsonify([_page_summary(p) for p in rows])


@app.route('/categories', methods=['GET'])
def list_categories():
    from sqlalchemy import func
    rows = db.session.query(Page.category, func.count(Page.id)).group_by(Page.category).all()
    return jsonify([{'category': c, 'count': n} for c, n in rows])


# ───────────────────────── 单页增删改查 ─────────────────────────
@app.route('/pages', methods=['POST'])
def create_page():
    data = request.get_json(force=True, silent=True) or {}
    title = (data.get('title') or '').strip() or '未命名'
    p = Page(
        title=title,
        category=(data.get('category') or '未分类').strip() or '未分类',
        tags=(data.get('tags') or '').strip(),
        content=(data.get('content') or ''),
    )
    db.session.add(p)
    db.session.commit()
    return jsonify({'id': p.id, 'title': p.title, 'category': p.category,
                    'tags': p.tags, 'content': p.content,
                    'created_at': p.created_at.isoformat(),
                    'updated_at': p.updated_at.isoformat()}), 201


@app.route('/pages/<int:pid>', methods=['GET'])
def get_page(pid):
    p = Page.query.get(pid)
    if not p:
        abort(404)
    return jsonify({'id': p.id, 'title': p.title, 'category': p.category,
                    'tags': p.tags, 'content': p.content,
                    'created_at': p.created_at.isoformat() if p.created_at else None,
                    'updated_at': p.updated_at.isoformat() if p.updated_at else None})


@app.route('/pages/<int:pid>', methods=['PUT'])
def update_page(pid):
    p = Page.query.get(pid)
    if not p:
        abort(404)
    data = request.get_json(force=True, silent=True) or {}
    if 'title' in data:
        p.title = (data['title'] or '').strip() or '未命名'
    if 'category' in data:
        p.category = (data['category'] or '未分类').strip() or '未分类'
    if 'tags' in data:
        p.tags = (data['tags'] or '').strip()
    if 'content' in data:
        p.content = data['content'] or ''
    p.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'id': p.id, 'title': p.title, 'category': p.category,
                    'tags': p.tags, 'content': p.content,
                    'updated_at': p.updated_at.isoformat()})


@app.route('/pages/<int:pid>', methods=['DELETE'])
def delete_page(pid):
    p = Page.query.get(pid)
    if not p:
        abort(404)
    db.session.delete(p)
    db.session.commit()
    return jsonify(ok=True)


# ───────────────────────── 附件（PDF 说明书 / 图片等） ─────────────────────────
ALLOWED_EXT = {
    '.pdf', '.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.svg',
    '.txt', '.md', '.csv', '.doc', '.docx', '.xls', '.xlsx', '.zip',
}


def _safe_ext(name):
    ext = os.path.splitext(name or '')[1].lower()
    return ext if ext in ALLOWED_EXT else None


@app.route('/pages/<int:pid>/attachments', methods=['GET'])
def list_attachments(pid):
    rows = Attachment.query.filter_by(page_id=pid).order_by(Attachment.id).all()
    return jsonify([
        {'id': r.id, 'page_id': r.page_id, 'name': r.original, 'mime': r.mime,
         'size': r.size, 'created_at': r.created_at.isoformat() if r.created_at else None}
        for r in rows
    ])


@app.route('/pages/<int:pid>/attachments', methods=['POST'])
def upload_attachment(pid):
    p = Page.query.get(pid)
    if not p:
        abort(404)
    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify(error='no file'), 400
    ext = _safe_ext(f.filename)
    if not ext:
        return jsonify(error='不支持的文件类型'), 400
    os.makedirs(ATTACH_DIR, exist_ok=True)
    stored = secrets.token_hex(12) + ext
    dest = os.path.join(ATTACH_DIR, stored)
    f.save(dest)
    size = os.path.getsize(dest)
    mime = mimetypes.guess_type(f.filename)[0] or 'application/octet-stream'
    a = Attachment(page_id=pid, filename=stored, original=f.filename, mime=mime, size=size)
    db.session.add(a)
    db.session.commit()
    return jsonify({'id': a.id, 'page_id': pid, 'name': a.original, 'mime': a.mime, 'size': a.size}), 201


@app.route('/attachments/<int:aid>/file', methods=['GET'])
def serve_attachment(aid):
    a = Attachment.query.get(aid)
    if not a:
        abort(404)
    path = os.path.join(ATTACH_DIR, a.filename)
    if not os.path.isfile(path):
        abort(404)
    return send_file(path, mimetype=a.mime or 'application/octet-stream',
                     as_attachment=False, conditional=True)


@app.route('/attachments/<int:aid>', methods=['DELETE'])
def delete_attachment(aid):
    a = Attachment.query.get(aid)
    if not a:
        abort(404)
    path = os.path.join(ATTACH_DIR, a.filename)
    try:
        if os.path.isfile(path):
            os.remove(path)
    except Exception:
        pass
    db.session.delete(a)
    db.session.commit()
    return jsonify(ok=True)


# ───────────────────────── 启动初始化 ─────────────────────────
if HAVE_SQLA:
    with app.app_context():
        os.makedirs(ATTACH_DIR, exist_ok=True)
        db.create_all()
        if Page.query.count() == 0:
            db.session.add(Page(
                title=SEED_TITLE, category=SEED_CATEGORY, tags='示例,入门',
                content=SEED_CONTENT))
            db.session.commit()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
