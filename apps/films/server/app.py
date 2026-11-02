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
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///./films.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app) if HAVE_SQLA else None


# ───────────────────────── 数据模型 ─────────────────────────
class Film(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    ftype = db.Column(db.String(20), default='电影')       # 电影/剧集/综艺/纪录片/其他
    platform = db.Column(db.String(60), default='其他')    # 平台
    status = db.Column(db.String(20), default='想看')      # 想看/在看/已看
    rating = db.Column(db.Integer, default=0)              # 0~5 星
    seasons = db.Column(db.Integer, default=0)             # 季数（剧集）
    episode = db.Column(db.Integer, default=0)             # 当前看到第几集
    year = db.Column(db.Integer, default=0)                # 年份
    notes = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ───────────────────────── 工具 ─────────────────────────
def _clamp_rating(v):
    try:
        v = int(v)
    except Exception:
        v = 0
    return max(0, min(5, v))


def _film_json(f):
    return {
        'id': f.id, 'title': f.title or '', 'ftype': f.ftype or '电影',
        'platform': f.platform or '其他', 'status': f.status or '想看',
        'rating': f.rating or 0, 'seasons': f.seasons or 0, 'episode': f.episode or 0,
        'year': f.year or 0, 'notes': f.notes or '',
        'created_at': f.created_at.isoformat() if f.created_at else None,
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
    return jsonify(ok=True, counts={'films': Film.query.count()} if HAVE_SQLA else {'films': 0})


# ───────────────────────── 影视管理 ─────────────────────────
@app.route('/films', methods=['GET'])
def list_films():
    q = (request.args.get('q') or '').strip()
    ft = (request.args.get('type') or '').strip()
    st = (request.args.get('status') or '').strip()
    query = Film.query
    if ft:
        query = query.filter_by(ftype=ft)
    if st:
        query = query.filter_by(status=st)
    if q:
        like = f'%{q}%'
        query = query.filter(Film.title.ilike(like))
    rows = query.order_by(Film.id.desc()).all()
    return jsonify([_film_json(f) for f in rows])


@app.route('/types', methods=['GET'])
def list_types():
    from sqlalchemy import func
    rows = db.session.query(Film.ftype, func.count(Film.id)).group_by(Film.ftype).all()
    return jsonify([{'type': t, 'count': n} for t, n in rows])


@app.route('/stats', methods=['GET'])
def stats():
    from sqlalchemy import func
    rows = db.session.query(Film.status, func.count(Film.id)).group_by(Film.status).all()
    out = {'想看': 0, '在看': 0, '已看': 0, 'total': Film.query.count()}
    for s, n in rows:
        out[s] = n
    return jsonify(out)


@app.route('/films', methods=['POST'])
def create_film():
    data = request.get_json(force=True, silent=True) or {}
    title = (data.get('title') or '').strip()
    if not title:
        return jsonify(error='片名必填'), 400
    f = Film(
        title=title,
        ftype=(data.get('ftype') or '电影').strip() or '电影',
        platform=(data.get('platform') or '其他').strip() or '其他',
        status=(data.get('status') or '想看').strip() or '想看',
        rating=_clamp_rating(data.get('rating')),
        seasons=int(data.get('seasons') or 0),
        episode=int(data.get('episode') or 0),
        year=int(data.get('year') or 0),
        notes=(data.get('notes') or '').strip(),
    )
    db.session.add(f)
    db.session.commit()
    return jsonify(_film_json(f)), 201


@app.route('/films/<int:fid>', methods=['GET'])
def get_film(fid):
    f = Film.query.get(fid)
    if not f:
        abort(404)
    return jsonify(_film_json(f))


@app.route('/films/<int:fid>', methods=['PUT'])
def update_film(fid):
    f = Film.query.get(fid)
    if not f:
        abort(404)
    data = request.get_json(force=True, silent=True) or {}
    if 'title' in data:
        f.title = (data['title'] or '').strip()
    if 'ftype' in data:
        f.ftype = (data['ftype'] or '电影').strip() or '电影'
    if 'platform' in data:
        f.platform = (data['platform'] or '其他').strip() or '其他'
    if 'status' in data:
        f.status = (data['status'] or '想看').strip() or '想看'
    if 'rating' in data:
        f.rating = _clamp_rating(data['rating'])
    if 'seasons' in data:
        f.seasons = int(data.get('seasons') or 0)
    if 'episode' in data:
        f.episode = int(data.get('episode') or 0)
    if 'year' in data:
        f.year = int(data.get('year') or 0)
    if 'notes' in data:
        f.notes = (data['notes'] or '').strip()
    db.session.commit()
    return jsonify(_film_json(f))


@app.route('/films/<int:fid>', methods=['DELETE'])
def delete_film(fid):
    f = Film.query.get(fid)
    if not f:
        abort(404)
    db.session.delete(f)
    db.session.commit()
    return jsonify(ok=True)


# ───────────────────────── 启动初始化 ─────────────────────────
if HAVE_SQLA:
    with app.app_context():
        db.create_all()
        if Film.query.count() == 0:
            samples = [
                ('星际穿越', '电影', '腾讯视频', '已看', 5, 0, 0, 2014, '诺兰的硬科幻，时间与爱的主题。'),
                ('繁花', '剧集', '腾讯视频', '在看', 4, 1, 18, 2023, '王家卫风格沪语剧，追剧中。'),
                ('地球脉动', '纪录片', 'B站', '想看', 0, 0, 0, 2006, '自然纪录片天花板，待刷。'),
            ]
            for t, ft, p, s, r, se, ep, y, nt in samples:
                db.session.add(Film(title=t, ftype=ft, platform=p, status=s, rating=r,
                                    seasons=se, episode=ep, year=y, notes=nt))
            db.session.commit()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
