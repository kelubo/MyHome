import os
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
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///./album.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = int(os.environ.get('ALBUM_MAX_UPLOAD', 100 * 1024 * 1024))  # 单文件上限 100MB

# 存储目录（容器内路径；docker-compose 已把 ./data/album 挂到这里）
DATA_DIR = os.environ.get('ALBUM_DATA_DIR', '/data/album')
PHOTO_DIR = os.path.join(DATA_DIR, 'photos')
THUMB_DIR = os.path.join(DATA_DIR, 'thumbs')
THUMB_SIZE = (400, 400)
THUMB_QUALITY = 82
ALLOWED_EXT = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}

db = SQLAlchemy(app) if HAVE_SQLA else None


# ───────────────────────── 数据模型 ─────────────────────────
class Album(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, default='未命名相册')
    description = db.Column(db.Text, default='')         # 简短说明（侧栏展示）
    notes = db.Column(db.Text, default='')               # 备注（较长，详情/编辑可见）
    cover_id = db.Column(db.Integer, nullable=True)     # 封面照片 id（可为空）
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Photo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    album_id = db.Column(db.Integer, nullable=True, index=True)
    title = db.Column(db.String(200), default='')
    description = db.Column(db.Text, default='')
    filename = db.Column(db.String(255), nullable=False)   # 原始图存储名（含扩展名，随机化防冲突/穿越）
    thumb = db.Column(db.String(255), default='')          # 缩略图文件名（生成失败则为空，前端回退原图）
    original = db.Column(db.String(300), default='')       # 原始文件名（展示用）
    mime = db.Column(db.String(120), default='')
    size = db.Column(db.Integer, default=0)
    width = db.Column(db.Integer, default=0)
    height = db.Column(db.Integer, default=0)
    taken_at = db.Column(db.DateTime, nullable=True)       # 拍摄时间（EXIF 自动读取，可手动编辑）
    location = db.Column(db.String(200), default='')       # 地点（EXIF GPS 自动读取为经纬度，可手动改地名）
    camera = db.Column(db.String(120), default='')         # 拍摄设备/相机（EXIF 自动读取）
    people = db.Column(db.String(200), default='')         # 人物（逗号分隔，手动填写）
    notes = db.Column(db.Text, default='')                 # 备注（较长自由文本）
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ───────────────────────── 工具 ─────────────────────────
def _make_thumbnail(src_path, dest_path):
    """用 Pillow 生成缩略图；任何失败都返回 False（前端回退用原图）。"""
    try:
        from PIL import Image, ImageOps
    except Exception:
        return False
    try:
        with Image.open(src_path) as im:
            im = ImageOps.exif_transpose(im)               # 按 EXIF 方向摆正
            im.thumbnail(THUMB_SIZE, Image.LANCZOS)
            im = im.convert('RGBA')
            bg = Image.new('RGBA', im.size, (255, 255, 255, 255))
            bg.alpha_composite(im)
            im = bg.convert('RGB')
            im.save(dest_path, 'JPEG', quality=THUMB_QUALITY)
        return True
    except Exception:
        return False


def _image_size(src_path):
    try:
        from PIL import Image
        with Image.open(src_path) as im:
            return im.size
    except Exception:
        return (0, 0)


def _gps_to_deg(val, ref):
    """EXIF GPS 经/纬度（RATIONALS 三元组 + 方向）转十进制度数。"""
    if not val:
        return None
    def r(x):
        if isinstance(x, (int, float)):
            return float(x)
        if hasattr(x, 'numerator'):
            return float(x.numerator) / float(x.denominator or 1)
        try:
            return float(x)
        except Exception:
            return 0.0
    try:
        deg = r(val[0]) + r(val[1]) / 60 + (r(val[2]) if len(val) > 2 else 0) / 3600
        if ref in ('S', 'W', 's', 'w'):
            deg = -deg
        return deg
    except Exception:
        return None


def _read_exif(src_path):
    """从图片 EXIF 读取拍摄时间 / 设备 / GPS 地点；任何异常都安全回退为 None。"""
    info = {'taken_at': None, 'camera': None, 'location': None}
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS
        with Image.open(src_path) as im:
            exif = im.getexif()
            if not exif:
                return info
            # 拍摄时间
            for tag in (36867, 36868, 306):       # DateTimeOriginal / DateTimeDigitized / DateTime
                val = exif.get(tag)
                if val:
                    try:
                        info['taken_at'] = datetime.strptime(val, '%Y:%m:%d %H:%M:%S')
                        break
                    except Exception:
                        pass
            # 设备（厂商 + 型号）
            make = exif.get(271)
            model = exif.get(272)
            cam = ' '.join(filter(None, [str(make or '').strip(), str(model or '').strip()])).strip()
            if cam:
                info['camera'] = cam
            # GPS 地点（转十进制度数，格式：纬度, 经度）
            try:
                gps = exif.get_ifd(0x8825)
                if gps:
                    lat = _gps_to_deg(gps.get(2), gps.get(1))
                    lon = _gps_to_deg(gps.get(4), gps.get(3))
                    if lat is not None and lon is not None:
                        info['location'] = '%.6f, %.6f' % (lat, lon)
            except Exception:
                pass
    except Exception:
        pass
    return info


def _safe_path(base_dir, fn):
    """校验文件名未逃离 base_dir（防目录穿越）。"""
    path = os.path.normpath(os.path.join(base_dir, fn))
    return path if path.startswith(base_dir) and os.path.isfile(path) else None


def _album_json(a):
    cover_thumb = cover_media = None
    if a.cover_id:
        cp = Photo.query.get(a.cover_id)
        if cp:
            cover_thumb = cp.thumb
            cover_media = cp.filename
    return {
        'id': a.id, 'name': a.name, 'description': a.description, 'notes': a.notes or '',
        'cover_id': a.cover_id, 'cover_thumb': cover_thumb, 'cover_media': cover_media,
        'count': Photo.query.filter_by(album_id=a.id).count(),
        'created_at': a.created_at.isoformat() if a.created_at else None,
    }


def _photo_json(p):
    return {
        'id': p.id, 'album_id': p.album_id, 'title': p.title, 'description': p.description,
        'original': p.original, 'mime': p.mime, 'size': p.size,
        'width': p.width, 'height': p.height,
        'taken_at': p.taken_at.isoformat() if p.taken_at else None,
        'location': p.location or '', 'camera': p.camera or '', 'people': p.people or '',
        'notes': p.notes or '',
        'created_at': p.created_at.isoformat() if p.created_at else None,
        'filename': p.filename,
        'thumb': p.thumb or '',    # 前端自行拼 /thumbs/ 或回退 /media/
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
    if HAVE_SQLA:
        counts = {'photos': Photo.query.count(), 'albums': Album.query.count()}
    else:
        counts = {'photos': 0, 'albums': 0}
    return jsonify(ok=True, counts=counts)


# ───────────────────────── 相册管理 ─────────────────────────
@app.route('/albums', methods=['GET'])
def list_albums():
    rows = Album.query.order_by(Album.created_at.desc()).all()
    return jsonify([_album_json(a) for a in rows])


@app.route('/albums', methods=['POST'])
def create_album():
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get('name') or '').strip() or '未命名相册'
    a = Album(name=name, description=(data.get('description') or '').strip())
    db.session.add(a)
    db.session.commit()
    return jsonify(_album_json(a)), 201


@app.route('/albums/<int:aid>', methods=['GET'])
def get_album(aid):
    a = Album.query.get(aid)
    if not a:
        abort(404)
    return jsonify(_album_json(a))


@app.route('/albums/<int:aid>', methods=['PUT'])
def update_album(aid):
    a = Album.query.get(aid)
    if not a:
        abort(404)
    data = request.get_json(force=True, silent=True) or {}
    if 'name' in data:
        a.name = (data['name'] or '').strip() or '未命名相册'
    if 'description' in data:
        a.description = (data['description'] or '').strip()
    if 'notes' in data:
        a.notes = (data['notes'] or '').strip()
    if 'cover_id' in data:
        v = data['cover_id']
        a.cover_id = int(v) if v not in (None, '', 0) else None
    db.session.commit()
    return jsonify(_album_json(a))


@app.route('/albums/<int:aid>', methods=['DELETE'])
def delete_album(aid):
    a = Album.query.get(aid)
    if not a:
        abort(404)
    for p in Photo.query.filter_by(album_id=aid).all():
        _remove_photo_files(p)
        db.session.delete(p)
    db.session.delete(a)
    db.session.commit()
    return jsonify(ok=True)


# ───────────────────────── 照片管理 ─────────────────────────
@app.route('/photos', methods=['GET'])
def list_photos():
    album_id = request.args.get('album_id')
    q = (request.args.get('q') or '').strip()
    query = Photo.query
    if album_id is not None and album_id != '':
        try:
            query = query.filter_by(album_id=int(album_id))
        except Exception:
            pass
    if q:
        like = '%' + q + '%'
        query = query.filter(db.or_(
            Photo.title.ilike(like),
            Photo.description.ilike(like),
            Photo.original.ilike(like),
        ))
    rows = query.order_by(Photo.created_at.desc()).all()
    return jsonify([_photo_json(p) for p in rows])


@app.route('/photos/upload', methods=['POST'])
def upload_photos():
    album_id = request.form.get('album_id') or None
    if album_id is not None:
        try:
            album_id = int(album_id)
        except Exception:
            album_id = None
    files = request.files.getlist('files')
    if not files:
        f = request.files.get('file')
        if f:
            files = [f]
    if not files:
        return jsonify(error='no file'), 400
    os.makedirs(PHOTO_DIR, exist_ok=True)
    os.makedirs(THUMB_DIR, exist_ok=True)
    ids = []
    for f in files:
        if not f.filename:
            continue
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in ALLOWED_EXT:
            continue
        token = secrets.token_hex(12)
        stored = token + ext
        dest = os.path.join(PHOTO_DIR, stored)
        f.save(dest)
        size = os.path.getsize(dest)
        mime = mimetypes.guess_type(f.filename)[0] or 'image/jpeg'
        thumb_name = token + '.thumb.jpg'
        if not _make_thumbnail(dest, os.path.join(THUMB_DIR, thumb_name)):
            thumb_name = ''
        w, h = _image_size(dest)
        ex = _read_exif(dest)
        ph = Photo(album_id=album_id, title='', description='', filename=stored,
                   thumb=thumb_name, original=f.filename, mime=mime, size=size,
                   width=w, height=h, taken_at=ex['taken_at'], location=ex['location'] or '',
                   camera=ex['camera'] or '')
        db.session.add(ph)
        db.session.commit()
        ids.append(ph.id)
    if not ids:
        return jsonify(error='没有可上传的图片（支持 jpg/png/gif/webp/bmp）'), 400
    return jsonify(ids=ids, count=len(ids)), 201


@app.route('/photos/<int:pid>', methods=['GET'])
def get_photo(pid):
    p = Photo.query.get(pid)
    if not p:
        abort(404)
    return jsonify(_photo_json(p))


@app.route('/photos/<int:pid>', methods=['PUT'])
def update_photo(pid):
    p = Photo.query.get(pid)
    if not p:
        abort(404)
    data = request.get_json(force=True, silent=True) or {}
    if 'title' in data:
        p.title = (data['title'] or '').strip()
    if 'description' in data:
        p.description = data.get('description') or ''
    if 'notes' in data:
        p.notes = data.get('notes') or ''
    if 'location' in data:
        p.location = (data['location'] or '').strip()
    if 'camera' in data:
        p.camera = (data['camera'] or '').strip()
    if 'people' in data:
        p.people = (data['people'] or '').strip()
    if 'album_id' in data:
        v = data['album_id']
        p.album_id = int(v) if v not in (None, '', 0) else None
    if 'taken_at' in data and data['taken_at']:
        try:
            p.taken_at = datetime.fromisoformat(str(data['taken_at']).replace('Z', ''))
        except Exception:
            pass
    db.session.commit()
    return jsonify(_photo_json(p))


@app.route('/photos/<int:pid>', methods=['DELETE'])
def delete_photo(pid):
    p = Photo.query.get(pid)
    if not p:
        abort(404)
    _remove_photo_files(p)
    db.session.delete(p)
    db.session.commit()
    return jsonify(ok=True)


def _remove_photo_files(p):
    for d, fn in ((PHOTO_DIR, p.filename), (THUMB_DIR, p.thumb)):
        if not fn:
            continue
        try:
            fp = os.path.join(d, fn)
            if os.path.isfile(fp):
                os.remove(fp)
        except Exception:
            pass


# ───────────────────────── 媒体托管（经后端，不在 nginx 静态根暴露） ─────────────────────────
@app.route('/media/<path:fn>')
def serve_media(fn):
    path = _safe_path(PHOTO_DIR, fn)
    if not path:
        abort(404)
    return send_file(path, conditional=True)


@app.route('/thumbs/<path:fn>')
def serve_thumb(fn):
    path = _safe_path(THUMB_DIR, fn)
    if not path:
        abort(404)
    return send_file(path, conditional=True)


# ───────────────────────── 启动初始化 ─────────────────────────
def _ensure_columns():
    """兼容已存在的库：幂等补加新增列（ALTER TABLE ... ADD COLUMN IF NOT EXISTS）。"""
    stmts = [
        "ALTER TABLE album ADD COLUMN IF NOT EXISTS notes TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE photo ADD COLUMN IF NOT EXISTS location VARCHAR(200) NOT NULL DEFAULT ''",
        "ALTER TABLE photo ADD COLUMN IF NOT EXISTS camera VARCHAR(120) NOT NULL DEFAULT ''",
        "ALTER TABLE photo ADD COLUMN IF NOT EXISTS people VARCHAR(200) NOT NULL DEFAULT ''",
        "ALTER TABLE photo ADD COLUMN IF NOT EXISTS notes TEXT NOT NULL DEFAULT ''",
    ]
    for s in stmts:
        try:
            db.session.execute(db.text(s))
            db.session.commit()
        except Exception:
            db.session.rollback()


if HAVE_SQLA:
    with app.app_context():
        os.makedirs(PHOTO_DIR, exist_ok=True)
        os.makedirs(THUMB_DIR, exist_ok=True)
        db.create_all()
        _ensure_columns()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
