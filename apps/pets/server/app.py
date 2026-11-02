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
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///./pets.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app) if HAVE_SQLA else None


# ───────────────────────── 数据模型 ─────────────────────────
class Pet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(60), nullable=False)
    species = db.Column(db.String(20), default='其他')     # 狗/猫/其他
    breed = db.Column(db.String(60), default='')           # 品种
    birthday = db.Column(db.Date, nullable=True)           # 生日
    gender = db.Column(db.String(10), default='')          # 公/母/未知
    weight = db.Column(db.String(20), default='')          # 体重
    microchip = db.Column(db.String(40), default='')       # 芯片号
    vet = db.Column(db.String(120), default='')            # 常去宠物医院
    notes = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class CareRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pet_id = db.Column(db.Integer, db.ForeignKey('pet.id', ondelete='CASCADE'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    ctype = db.Column(db.String(30), default='其他')       # 喂食/驱虫/疫苗/体检/洗澡/其他
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


def _pet_json(p):
    return {
        'id': p.id, 'name': p.name or '', 'species': p.species or '其他',
        'breed': p.breed or '', 'birthday': p.birthday.isoformat() if p.birthday else '',
        'gender': p.gender or '', 'weight': p.weight or '', 'microchip': p.microchip or '',
        'vet': p.vet or '', 'notes': p.notes or '',
        'created_at': p.created_at.isoformat() if p.created_at else None,
    }


def _care_json(c):
    return {
        'id': c.id, 'pet_id': c.pet_id, 'date': c.date.isoformat() if c.date else '',
        'ctype': c.ctype or '其他', 'note': c.note or '',
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
    return jsonify(ok=True, counts={'pets': Pet.query.count()} if HAVE_SQLA else {'pets': 0})


# ───────────────────────── 宠物管理 ─────────────────────────
@app.route('/pets', methods=['GET'])
def list_pets():
    rows = Pet.query.order_by(Pet.name).all()
    return jsonify([_pet_json(p) for p in rows])


@app.route('/pets', methods=['POST'])
def create_pet():
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify(error='宠物名字必填'), 400
    p = Pet(
        name=name,
        species=(data.get('species') or '其他').strip() or '其他',
        breed=(data.get('breed') or '').strip(),
        birthday=_parse_date(data.get('birthday')),
        gender=(data.get('gender') or '').strip(),
        weight=(data.get('weight') or '').strip(),
        microchip=(data.get('microchip') or '').strip(),
        vet=(data.get('vet') or '').strip(),
        notes=(data.get('notes') or '').strip(),
    )
    db.session.add(p)
    db.session.commit()
    return jsonify(_pet_json(p)), 201


@app.route('/pets/<int:pid>', methods=['GET'])
def get_pet(pid):
    p = Pet.query.get(pid)
    if not p:
        abort(404)
    return jsonify(_pet_json(p))


@app.route('/pets/<int:pid>', methods=['PUT'])
def update_pet(pid):
    p = Pet.query.get(pid)
    if not p:
        abort(404)
    data = request.get_json(force=True, silent=True) or {}
    if 'name' in data:
        p.name = (data['name'] or '').strip()
    if 'species' in data:
        p.species = (data['species'] or '其他').strip() or '其他'
    if 'breed' in data:
        p.breed = (data['breed'] or '').strip()
    if 'birthday' in data:
        p.birthday = _parse_date(data['birthday'])
    if 'gender' in data:
        p.gender = (data['gender'] or '').strip()
    if 'weight' in data:
        p.weight = (data['weight'] or '').strip()
    if 'microchip' in data:
        p.microchip = (data['microchip'] or '').strip()
    if 'vet' in data:
        p.vet = (data['vet'] or '').strip()
    if 'notes' in data:
        p.notes = (data['notes'] or '').strip()
    db.session.commit()
    return jsonify(_pet_json(p))


@app.route('/pets/<int:pid>', methods=['DELETE'])
def delete_pet(pid):
    p = Pet.query.get(pid)
    if not p:
        abort(404)
    CareRecord.query.filter_by(pet_id=pid).delete()
    db.session.delete(p)
    db.session.commit()
    return jsonify(ok=True)


# ───────────────────────── 照护记录 ─────────────────────────
@app.route('/pets/<int:pid>/care', methods=['GET'])
def list_care(pid):
    rows = CareRecord.query.filter_by(pet_id=pid).order_by(CareRecord.date.desc()).all()
    return jsonify([_care_json(c) for c in rows])


@app.route('/pets/<int:pid>/care', methods=['POST'])
def add_care(pid):
    if not Pet.query.get(pid):
        abort(404)
    data = request.get_json(force=True, silent=True) or {}
    d = _parse_date(data.get('date'))
    if not d:
        return jsonify(error='日期必填'), 400
    c = CareRecord(
        pet_id=pid, date=d,
        ctype=(data.get('ctype') or '其他').strip() or '其他',
        note=(data.get('note') or '').strip(),
    )
    db.session.add(c)
    db.session.commit()
    return jsonify(_care_json(c)), 201


@app.route('/care/<int:cid>', methods=['DELETE'])
def delete_care(cid):
    c = CareRecord.query.get(cid)
    if not c:
        abort(404)
    db.session.delete(c)
    db.session.commit()
    return jsonify(ok=True)


# ───────────────────────── 启动初始化 ─────────────────────────
if HAVE_SQLA:
    with app.app_context():
        db.create_all()
        if Pet.query.count() == 0:
            p = Pet(name='豆豆', species='狗', breed='柯基', birthday=date.today().replace(year=date.today().year-2, month=6, day=1),
                    gender='公', weight='12 kg', vet='社区宠物医院', notes='性格亲人，爱吃鸡肉干。')
            db.session.add(p)
            db.session.commit()
            for ctype, note in [('疫苗', '年度狂犬疫苗'), ('驱虫', '体内外驱虫'), ('洗澡', '宠物店洗澡')]:
                db.session.add(CareRecord(pet_id=p.id, date=date.today().replace(month=date.today().month-1 or 12), ctype=ctype, note=note))
            db.session.commit()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
