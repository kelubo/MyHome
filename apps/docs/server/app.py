import os
import secrets
import mimetypes
from datetime import datetime, date

from flask import Flask, request, jsonify, abort, send_file

try:
    from flask_sqlalchemy import SQLAlchemy
    HAVE_SQLA = True
except Exception:
    HAVE_SQLA = False

app = Flask(__name__)
# 集成模式由 docker-compose 注入 DATABASE_URL（PostgreSQL）；本地缺省回退到 SQLite 文件
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///./docs.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = int(os.environ.get('DOCS_MAX_UPLOAD', 50 * 1024 * 1024))  # 单文件上限 50MB
# 文档文件存储目录（容器内路径；docker-compose 已把 ./data/docs 挂到这里）
DOCS_DIR = os.environ.get('DOCS_DATA_DIR', '/data/docs')
db = SQLAlchemy(app) if HAVE_SQLA else None


# ───────────────────────── 数据模型 ─────────────────────────
class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False, default='未命名文档')
    category = db.Column(db.String(60), default='其他')       # 合同/证件/保修卡/说明书/其他
    description = db.Column(db.Text, default='')
    doc_date = db.Column(db.Date, nullable=True)             # 签署/到期/办理日期
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class DocFile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    doc_id = db.Column(db.Integer, nullable=False, index=True)
    filename = db.Column(db.String(255), nullable=False)      # 存储名（随机化，防冲突/穿越）
    original = db.Column(db.String(300), default='')         # 原始文件名（展示用）
    mime = db.Column(db.String(120), default='')
    size = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ───────────────────────── 工具 ─────────────────────────
ALLOWED_EXT = {
    '.pdf', '.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.svg',
    '.tif', '.tiff', '.txt', '.md', '.csv', '.doc', '.docx', '.xls', '.xlsx', '.zip',
}


def _safe_ext(name):
    ext = os.path.splitext(name or '')[1].lower()
    return ext if ext in ALLOWED_EXT else None


def _parse_date(s):
    if isinstance(s, date) and not isinstance(s, datetime):
        return s
    if isinstance(s, datetime):
        return s.date()
    try:
        return datetime.strptime(str(s)[:10], '%Y-%m-%d').date()
    except Exception:
        return None


def _doc_json(d):
    fc = DocFile.query.filter_by(doc_id=d.id).count() if HAVE_SQLA else 0
    return {
        'id': d.id, 'title': d.title, 'category': d.category or '其他',
        'description': d.description or '', 'doc_date': d.doc_date.isoformat() if d.doc_date else '',
        'file_count': fc,
        'created_at': d.created_at.isoformat() if d.created_at else None,
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
    return jsonify(ok=True, counts={'documents': Document.query.count()} if HAVE_SQLA else {'documents': 0})


# ───────────────────────── 文档管理 ─────────────────────────
@app.route('/documents', methods=['GET'])
def list_documents():
    cat = (request.args.get('category') or '').strip()
    q = Document.query
    if cat:
        q = q.filter_by(category=cat)
    rows = q.order_by(Document.doc_date.desc().nullslast(), Document.created_at.desc()).all()
    return jsonify([_doc_json(d) for d in rows])


@app.route('/categories', methods=['GET'])
def list_categories():
    from sqlalchemy import func
    rows = db.session.query(Document.category, func.count(Document.id)).group_by(Document.category).all()
    return jsonify([{'category': c, 'count': n} for c, n in rows])


@app.route('/documents', methods=['POST'])
def create_document():
    data = request.get_json(force=True, silent=True) or {}
    title = (data.get('title') or '').strip() or '未命名文档'
    d = Document(
        title=title,
        category=(data.get('category') or '其他').strip() or '其他',
        description=(data.get('description') or '').strip(),
        doc_date=_parse_date(data.get('doc_date')),
    )
    db.session.add(d)
    db.session.commit()
    return jsonify(_doc_json(d)), 201


@app.route('/documents/<int:did>', methods=['GET'])
def get_document(did):
    d = Document.query.get(did)
    if not d:
        abort(404)
    return jsonify(_doc_json(d))


@app.route('/documents/<int:did>', methods=['PUT'])
def update_document(did):
    d = Document.query.get(did)
    if not d:
        abort(404)
    data = request.get_json(force=True, silent=True) or {}
    if 'title' in data:
        d.title = (data['title'] or '').strip() or '未命名文档'
    if 'category' in data:
        d.category = (data['category'] or '其他').strip() or '其他'
    if 'description' in data:
        d.description = (data['description'] or '').strip()
    if 'doc_date' in data:
        d.doc_date = _parse_date(data['doc_date'])
    db.session.commit()
    return jsonify(_doc_json(d))


@app.route('/documents/<int:did>', methods=['DELETE'])
def delete_document(did):
    d = Document.query.get(did)
    if not d:
        abort(404)
    for f in DocFile.query.filter_by(doc_id=did).all():
        _remove_file(f)
        db.session.delete(f)
    db.session.delete(d)
    db.session.commit()
    return jsonify(ok=True)


# ───────────────────────── 文件（PDF/图片/扫描件） ─────────────────────────
@app.route('/documents/<int:did>/files', methods=['GET'])
def list_files(did):
    rows = DocFile.query.filter_by(doc_id=did).order_by(DocFile.id).all()
    return jsonify([
        {'id': r.id, 'doc_id': r.doc_id, 'name': r.original, 'mime': r.mime,
         'size': r.size, 'created_at': r.created_at.isoformat() if r.created_at else None}
        for r in rows
    ])


@app.route('/documents/<int:did>/files', methods=['POST'])
def upload_files(did):
    d = Document.query.get(did)
    if not d:
        abort(404)
    files = request.files.getlist('file')
    if not files:
        return jsonify(error='no file'), 400
    os.makedirs(DOCS_DIR, exist_ok=True)
    out = []
    for f in files:
        if not f or not f.filename:
            continue
        ext = _safe_ext(f.filename)
        if not ext:
            continue
        stored = secrets.token_hex(12) + ext
        dest = os.path.join(DOCS_DIR, stored)
        f.save(dest)
        size = os.path.getsize(dest)
        mime = mimetypes.guess_type(f.filename)[0] or 'application/octet-stream'
        r = DocFile(doc_id=did, filename=stored, original=f.filename, mime=mime, size=size)
        db.session.add(r)
        out.append({'id': r.id, 'name': r.original, 'mime': r.mime, 'size': r.size})
    db.session.commit()
    return jsonify(out), 201


def _remove_file(r):
    path = os.path.join(DOCS_DIR, r.filename)
    try:
        if os.path.isfile(path):
            os.remove(path)
    except Exception:
        pass


@app.route('/files/<int:fid>/file', methods=['GET'])
def serve_file(fid):
    r = DocFile.query.get(fid)
    if not r:
        abort(404)
    path = os.path.join(DOCS_DIR, r.filename)
    if not os.path.isfile(path):
        abort(404)
    return send_file(path, mimetype=r.mime or 'application/octet-stream',
                     as_attachment=False, conditional=True)


@app.route('/files/<int:fid>', methods=['DELETE'])
def delete_file(fid):
    r = DocFile.query.get(fid)
    if not r:
        abort(404)
    _remove_file(r)
    db.session.delete(r)
    db.session.commit()
    return jsonify(ok=True)


# ───────────────────────── 启动初始化 ─────────────────────────
if HAVE_SQLA:
    with app.app_context():
        os.makedirs(DOCS_DIR, exist_ok=True)
        db.create_all()
        if Document.query.count() == 0:
            db.session.add(Document(
                title='示例：家庭宽带合同', category='合同',
                description='中国电信宽带两年合约，附在办业务回执扫描件。',
                doc_date=date.today().replace(month=1, day=1)))
            db.session.commit()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
