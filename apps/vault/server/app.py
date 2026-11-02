import os
from datetime import datetime

from flask import Flask, request, jsonify, abort

try:
    from flask_sqlalchemy import SQLAlchemy
    HAVE_SQLA = True
except Exception:
    HAVE_SQLA = False

try:
    from cryptography.fernet import Fernet
    HAVE_CRYPTO = True
except Exception:
    HAVE_CRYPTO = False

app = Flask(__name__)
# 集成模式由 docker-compose 注入 DATABASE_URL（PostgreSQL）；本地缺省回退到 SQLite 文件
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///./vault.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app) if HAVE_SQLA else None


# ───────────────────────── 加密（敏感字段落库前加密） ─────────────────────────
# 密钥优先级：环境变量 VAULT_KEY（Fernet key）> 落盘文件 ./data/vault/vault.key。
# 若都不可用（本地未配置），退化为 base64 混淆并置 WARNING（不安全，仅本地调试）。
VAULT_DIR = os.environ.get('VAULT_DIR', '/data/vault')
KEY_FILE = os.path.join(VAULT_DIR, 'vault.key')
WARNING = False
_FERNET = None


def _load_key():
    global WARNING, _FERNET
    if not HAVE_CRYPTO:
        WARNING = True
        return None
    try:
        os.makedirs(VAULT_DIR, exist_ok=True)
        if os.path.exists(KEY_FILE):
            with open(KEY_FILE, 'rb') as f:
                key = f.read().strip()
        else:
            key = Fernet.generate_key()
            with open(KEY_FILE, 'wb') as f:
                f.write(key)
            try:
                os.chmod(KEY_FILE, 0o600)
            except Exception:
                pass
        _FERNET = Fernet(key)
        return key
    except Exception:
        WARNING = True
        return None


def enc(s):
    s = s or ''
    if _FERNET is not None:
        return _FERNET.encrypt(s.encode('utf-8')).decode('utf-8')
    import base64
    return base64.b64encode(s.encode('utf-8')).decode('utf-8')   # 不安全退化


def dec(s):
    if not s:
        return ''
    try:
        if _FERNET is not None:
            return _FERNET.decrypt(s.encode('utf-8')).decode('utf-8')
        import base64
        return base64.b64decode(s.encode('utf-8')).decode('utf-8')
    except Exception:
        return ''


_load_key()


# ───────────────────────── 数据模型 ─────────────────────────
class Secret(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)   # 明文（便于展示/搜索）
    category = db.Column(db.String(60), default='其他')  # 明文（便于筛选）
    username = db.Column(db.Text, default='')            # 加密
    password = db.Column(db.Text, default='')            # 加密
    url = db.Column(db.Text, default='')                 # 加密
    notes = db.Column(db.Text, default='')               # 加密
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ───────────────────────── 工具 ─────────────────────────
def _secret_json(s):
    return {
        'id': s.id, 'title': s.title or '', 'category': s.category or '其他',
        'username': dec(s.username), 'password': dec(s.password),
        'url': dec(s.url), 'notes': dec(s.notes),
        'created_at': s.created_at.isoformat() if s.created_at else None,
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
    return jsonify(ok=True, counts={'secrets': Secret.query.count() if HAVE_SQLA else 0},
                   crypto=HAVE_CRYPTO, warning=WARNING)


# ───────────────────────── 密码条目管理 ─────────────────────────
@app.route('/secrets', methods=['GET'])
def list_secrets():
    cat = (request.args.get('category') or '').strip()
    q = (request.args.get('q') or '').strip()
    query = Secret.query
    if cat:
        query = query.filter_by(category=cat)
    if q:
        like = f'%{q}%'
        query = query.filter(db.or_(Secret.title.ilike(like), Secret.category.ilike(like)))
    rows = query.order_by(Secret.id.desc()).all()
    return jsonify([_secret_json(s) for s in rows])


@app.route('/categories', methods=['GET'])
def list_categories():
    from sqlalchemy import func
    rows = db.session.query(Secret.category, func.count(Secret.id)).group_by(Secret.category).all()
    return jsonify([{'category': c, 'count': n} for c, n in rows])


@app.route('/secrets', methods=['POST'])
def create_secret():
    data = request.get_json(force=True, silent=True) or {}
    title = (data.get('title') or '').strip()
    if not title:
        return jsonify(error='标题必填'), 400
    s = Secret(
        title=title,
        category=(data.get('category') or '其他').strip() or '其他',
        username=enc(data.get('username')),
        password=enc(data.get('password')),
        url=enc(data.get('url')),
        notes=enc(data.get('notes')),
    )
    db.session.add(s)
    db.session.commit()
    return jsonify(_secret_json(s)), 201


@app.route('/secrets/<int:sid>', methods=['GET'])
def get_secret(sid):
    s = Secret.query.get(sid)
    if not s:
        abort(404)
    return jsonify(_secret_json(s))


@app.route('/secrets/<int:sid>', methods=['PUT'])
def update_secret(sid):
    s = Secret.query.get(sid)
    if not s:
        abort(404)
    data = request.get_json(force=True, silent=True) or {}
    if 'title' in data:
        s.title = (data['title'] or '').strip()
    if 'category' in data:
        s.category = (data['category'] or '其他').strip() or '其他'
    if 'username' in data:
        s.username = enc(data['username'])
    if 'password' in data:
        s.password = enc(data['password'])
    if 'url' in data:
        s.url = enc(data['url'])
    if 'notes' in data:
        s.notes = enc(data['notes'])
    db.session.commit()
    return jsonify(_secret_json(s))


@app.route('/secrets/<int:sid>', methods=['DELETE'])
def delete_secret(sid):
    s = Secret.query.get(sid)
    if not s:
        abort(404)
    db.session.delete(s)
    db.session.commit()
    return jsonify(ok=True)


# ───────────────────────── 启动初始化 ─────────────────────────
if HAVE_SQLA:
    with app.app_context():
        db.create_all()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
