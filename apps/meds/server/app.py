import os
import json
from datetime import datetime, date, timedelta

from flask import Flask, request, jsonify, abort

try:
    from flask_sqlalchemy import SQLAlchemy
    HAVE_SQLA = True
except Exception:
    HAVE_SQLA = False

app = Flask(__name__)
# 集成模式由 docker-compose 注入 DATABASE_URL（PostgreSQL）；本地缺省回退到 SQLite 文件
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///./meds.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app) if HAVE_SQLA else None


# ───────────────────────── 数据模型 ─────────────────────────
# MedPlan：服药计划（谁、吃什么药、剂量、频次、每天哪些时间点）
# MedLog ：某天某时间点的打卡记录（吃了没吃）
class MedPlan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    member = db.Column(db.String(60), default='')            # 成员：爸爸/妈妈/宝宝
    medicine = db.Column(db.String(120), nullable=False)     # 药品名称
    dosage = db.Column(db.String(60), default='')            # 剂量：1片 / 5ml
    frequency = db.Column(db.String(40), default='每日1次')  # 频次说明
    time_slots = db.Column(db.Text, default='["08:00"]')    # 服药时间点 JSON，如 ["08:00","20:00"]
    start_date = db.Column(db.Date, nullable=True)           # 开始日
    end_date = db.Column(db.Date, nullable=True)             # 结束日（长期留空）
    active = db.Column(db.Boolean, default=True)             # 是否启用
    notes = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class MedLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.Integer, db.ForeignKey('med_plan.id'), nullable=False)
    scheduled_date = db.Column(db.Date, nullable=False)      # 计划日期
    scheduled_time = db.Column(db.String(8), default='')     # 计划时间 HH:MM
    taken = db.Column(db.Boolean, default=False)             # 是否服药
    taken_at = db.Column(db.DateTime, nullable=True)         # 实际服药时间
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


def _slots(plan):
    try:
        sl = json.loads(plan.time_slots or '[]')
        if isinstance(sl, list) and sl:
            return [str(x) for x in sl]
    except Exception:
        pass
    return ['08:00']


def _plan_json(p):
    return {
        'id': p.id, 'member': p.member or '', 'medicine': p.medicine or '',
        'dosage': p.dosage or '', 'frequency': p.frequency or '每日1次',
        'time_slots': _slots(p),
        'start_date': p.start_date.isoformat() if p.start_date else '',
        'end_date': p.end_date.isoformat() if p.end_date else '',
        'active': bool(p.active),
        'notes': p.notes or '',
        'created_at': p.created_at.isoformat() if p.created_at else None,
    }


def _log_json(l):
    return {
        'id': l.id, 'plan_id': l.plan_id,
        'scheduled_date': l.scheduled_date.isoformat() if l.scheduled_date else '',
        'scheduled_time': l.scheduled_time or '',
        'taken': bool(l.taken),
        'taken_at': l.taken_at.isoformat() if l.taken_at else '',
        'note': l.note or '',
    }


def _in_range(p, d):
    if p.start_date and p.start_date > d:
        return False
    if p.end_date and p.end_date < d:
        return False
    return True


# ───────────────────────── 通用 ─────────────────────────
@app.after_request
def _cors(resp):
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Access-Control-Allow-Methods'] = 'GET,POST,PUT,DELETE,OPTIONS'
    resp.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return resp


@app.route('/health')
def health():
    return jsonify(ok=True, counts={'plans': MedPlan.query.count()} if HAVE_SQLA else {'plans': 0})


# ───────────────────────── 服药计划 CRUD ─────────────────────────
@app.route('/plans', methods=['GET'])
def list_plans():
    q = (request.args.get('q') or '').strip()
    query = MedPlan.query
    if q:
        like = f'%{q}%'
        query = query.filter(db.or_(MedPlan.medicine.ilike(like), MedPlan.member.ilike(like),
                                    MedPlan.notes.ilike(like)))
    rows = query.order_by(MedPlan.id.desc()).all()
    return jsonify([_plan_json(r) for r in rows])


@app.route('/plans', methods=['POST'])
def create_plan():
    data = request.get_json(force=True, silent=True) or {}
    medicine = (data.get('medicine') or '').strip()
    if not medicine:
        return jsonify(error='药品名称必填'), 400
    slots = data.get('time_slots')
    if isinstance(slots, list):
        slots_json = json.dumps(slots, ensure_ascii=False)
    else:
        slots_json = str(slots or '["08:00"]')
    p = MedPlan(
        member=(data.get('member') or '').strip(),
        medicine=medicine,
        dosage=(data.get('dosage') or '').strip(),
        frequency=(data.get('frequency') or '每日1次').strip() or '每日1次',
        time_slots=slots_json,
        start_date=_parse_date(data.get('start_date')),
        end_date=_parse_date(data.get('end_date')),
        active=bool(data.get('active', True)),
        notes=(data.get('notes') or '').strip(),
    )
    db.session.add(p)
    db.session.commit()
    return jsonify(_plan_json(p)), 201


@app.route('/plans/<int:pid>', methods=['GET'])
def get_plan(pid):
    p = MedPlan.query.get(pid)
    if not p:
        abort(404)
    return jsonify(_plan_json(p))


@app.route('/plans/<int:pid>', methods=['PUT'])
def update_plan(pid):
    p = MedPlan.query.get(pid)
    if not p:
        abort(404)
    data = request.get_json(force=True, silent=True) or {}
    if 'medicine' in data:
        p.medicine = (data['medicine'] or '').strip() or p.medicine
    if 'member' in data:
        p.member = (data['member'] or '').strip()
    if 'dosage' in data:
        p.dosage = (data['dosage'] or '').strip()
    if 'frequency' in data:
        p.frequency = (data['frequency'] or '每日1次').strip() or '每日1次'
    if 'time_slots' in data:
        sl = data['time_slots']
        p.time_slots = json.dumps(sl, ensure_ascii=False) if isinstance(sl, list) else str(sl or '["08:00"]')
    if 'start_date' in data:
        p.start_date = _parse_date(data['start_date'])
    if 'end_date' in data:
        p.end_date = _parse_date(data['end_date'])
    if 'active' in data:
        p.active = bool(data['active'])
    if 'notes' in data:
        p.notes = (data['notes'] or '').strip()
    db.session.commit()
    return jsonify(_plan_json(p))


@app.route('/plans/<int:pid>', methods=['DELETE'])
def delete_plan(pid):
    p = MedPlan.query.get(pid)
    if not p:
        abort(404)
    MedLog.query.filter_by(plan_id=pid).delete()
    db.session.delete(p)
    db.session.commit()
    return jsonify(ok=True)


# ───────────────────────── 打卡 ─────────────────────────
@app.route('/today', methods=['GET'])
def today():
    d = _parse_date(request.args.get('date')) or date.today()
    plans = MedPlan.query.filter_by(active=True).all()
    out = []
    for p in plans:
        if not _in_range(p, d):
            continue
        for t in _slots(p):
            log = MedLog.query.filter_by(plan_id=p.id, scheduled_date=d, scheduled_time=t).first()
            out.append({
                'plan_id': p.id, 'member': p.member or '', 'medicine': p.medicine,
                'dosage': p.dosage or '', 'time': t,
                'taken': bool(log.taken) if log else False,
                'taken_at': log.taken_at.isoformat() if log and log.taken_at else '',
                'log_id': log.id if log else None,
                'note': log.note if log else '',
            })
    out.sort(key=lambda x: x['time'])
    return jsonify({'date': d.isoformat(), 'items': out})


@app.route('/logs', methods=['GET'])
def list_logs():
    plan_id = request.args.get('plan_id')
    d = request.args.get('date')
    query = MedLog.query
    if plan_id:
        query = query.filter_by(plan_id=int(plan_id))
    if d:
        dd = _parse_date(d)
        if dd:
            query = query.filter_by(scheduled_date=dd)
    rows = query.order_by(MedLog.scheduled_date.desc(), MedLog.scheduled_time).all()
    return jsonify([_log_json(r) for r in rows])


@app.route('/logs', methods=['POST'])
def upsert_log():
    data = request.get_json(force=True, silent=True) or {}
    pid = int(data.get('plan_id'))
    sd = _parse_date(data.get('scheduled_date')) or date.today()
    st = (data.get('scheduled_time') or '').strip()
    taken = bool(data.get('taken', True))
    log = MedLog.query.filter_by(plan_id=pid, scheduled_date=sd, scheduled_time=st).first()
    if not log:
        log = MedLog(plan_id=pid, scheduled_date=sd, scheduled_time=st)
    log.taken = taken
    log.taken_at = datetime.utcnow() if taken else None
    log.note = (data.get('note') or '').strip()
    db.session.add(log)
    db.session.commit()
    return jsonify(_log_json(log)), 201


@app.route('/logs/<int:lid>', methods=['DELETE'])
def delete_log(lid):
    l = MedLog.query.get(lid)
    if not l:
        abort(404)
    db.session.delete(l)
    db.session.commit()
    return jsonify(ok=True)


@app.route('/stats', methods=['GET'])
def stats():
    d = date.today()
    plans = MedPlan.query.filter_by(active=True).all()
    total_due = 0
    done = 0
    missed = 0
    for p in plans:
        if not _in_range(p, d):
            continue
        for t in _slots(p):
            log = MedLog.query.filter_by(plan_id=p.id, scheduled_date=d, scheduled_time=t).first()
            if log:
                if log.taken:
                    done += 1
                else:
                    missed += 1
            else:
                total_due += 1
    return jsonify({'plans': len(plans), 'due': total_due, 'done': done, 'missed': missed})


# ───────────────────────── 启动初始化 ─────────────────────────
if HAVE_SQLA:
    with app.app_context():
        db.create_all()
        if MedPlan.query.count() == 0:
            t = date.today()
            samples = [
                ('爸爸', '降压药（氨氯地平）', '1片', '每日1次', ['08:00'], t - timedelta(days=30), None, '随早餐后服用'),
                ('宝宝', '维生素D滴剂', '1滴', '每日1次', ['09:00'], t - timedelta(days=60), None, '促进钙吸收'),
                ('妈妈', '二甲双胍', '1片', '每日2次', ['08:00', '20:00'], t - timedelta(days=20), None, '随餐服用'),
            ]
            for mb, md, dg, fr, sl, sd, ed, nt in samples:
                db.session.add(MedPlan(member=mb, medicine=md, dosage=dg, frequency=fr,
                                       time_slots=json.dumps(sl, ensure_ascii=False),
                                       start_date=sd, end_date=ed, active=True, notes=nt))
            db.session.commit()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
