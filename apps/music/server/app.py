import os
import re
import subprocess
import mimetypes
import threading
import json
import socket
import time
import shutil
from datetime import datetime

from flask import Flask, request, jsonify, Response, abort

try:
    from flask_sqlalchemy import SQLAlchemy
    HAVE_SQLA = True
except Exception:
    HAVE_SQLA = False

app = Flask(__name__)
# 集成模式由 docker-compose 注入 DATABASE_URL（PostgreSQL）；本地缺省回退到 SQLite 文件
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///./music.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app) if HAVE_SQLA else None


# ───────────────────────── 数据模型 ─────────────────────────
class Station(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    genre = db.Column(db.String(100), default='')
    custom = db.Column(db.Boolean, default=False)


class Favorite(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    source = db.Column(db.String(20), nullable=False)     # 'local' / 'nas名' / 'radio'
    lib_key = db.Column(db.String(40), default='')
    path = db.Column(db.String(1000), default='')          # 对 radio 为流地址
    title = db.Column(db.String(300), default='')
    artist = db.Column(db.String(300), default='')
    album = db.Column(db.String(300), default='')
    added = db.Column(db.DateTime, default=datetime.utcnow)


class NasMount(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)   # 标签 / 库 key
    protocol = db.Column(db.String(10), nullable=False)            # smb / nfs
    host = db.Column(db.String(200), nullable=False)
    share = db.Column(db.String(200), nullable=False)
    username = db.Column(db.String(100), default='')
    password = db.Column(db.String(200), default='')
    mount_path = db.Column(db.String(300), nullable=False)         # 容器内绝对路径
    status = db.Column(db.String(20), default='unmounted')         # mounting/mounted/error/unmounted
    error = db.Column(db.String(300), default='')


DEFAULTS = [
    ("SomaFM Groove Salad",   "https://ice1.somafm.com/groovesalad-128-mp3",   "Ambient / Downtempo"),
    ("SomaFM Drone Zone",     "https://ice1.somafm.com/dronezone-128-mp3",     "Ambient"),
    ("SomaFM Secret Agent",   "https://ice1.somafm.com/secretagent-128-mp3",    "Jazz / Lounge"),
    ("SomaFM Lush",           "https://ice1.somafm.com/lush-128-mp3",          "Vocal / Lounge"),
    ("SomaFM Sonic Universe", "https://ice1.somafm.com/sonicuniverse-128-mp3", "Jazz"),
    ("SomaFM Indie Pop Rocks","https://ice1.somafm.com/indiepop-128-mp3",      "Indie Pop"),
    ("SomaFM Space Station",  "https://ice1.somafm.com/spacestation-128-mp3",  "Space Age"),
    ("SomaFM Boot Liquor",    "https://ice1.somafm.com/bootliquor-128-mp3",    "Americana"),
]


# ───────────────────────── 音乐库配置 ─────────────────────────
# 环境变量 MUSIC_LIBRARIES 形如： key:标签:容器路径,key2:标签2:路径2
# 默认把 ./data/music 挂到 /music/local；NAS 由用户在 Web 页面动态挂载到 /music/nas-<名>
AUDIO_EXTS = {
    'mp3', 'flac', 'wav', 'ogg', 'oga', 'm4a', 'aac', 'opus',
    'wma', 'ape', 'tta', 'mpc', 'alac', 'aiff', 'aif',
}
NAS_BASE = '/music'


def _validate_host(s):
    return bool(re.match(r'^[A-Za-z0-9.\-]+$', s or ''))


def _validate_share(s):
    return bool(re.match(r'^[A-Za-z0-9._\/\-]+$', s or ''))


def _safe_mount_name(name):
    s = re.sub(r'[^A-Za-z0-9_\-]', '', name or '')
    return s or 'nas'


def get_libraries():
    raw = os.environ.get('MUSIC_LIBRARIES', 'local:本地音乐:/music/local')
    libs = []
    for part in raw.split(','):
        part = part.strip()
        if not part:
            continue
        segs = part.split(':', 2)
        if len(segs) >= 3:
            key, label, path = segs[0], segs[1], segs[2]
        elif len(segs) == 2:
            key, label, path = segs[0], segs[0], segs[1]
        else:
            key = label = path = segs[0]
        libs.append({
            'key': key,
            'label': label,
            'path': path,
            'available': os.path.isdir(path),
            'kind': 'local',
        })
    # 合并 Web 页面挂载的 NAS 音乐源
    if HAVE_SQLA:
        try:
            for m in NasMount.query.all():
                mp = m.mount_path
                libs.append({
                    'key': m.name,
                    'label': m.name,
                    'path': mp,
                    'available': os.path.isdir(mp) and os.path.ismount(mp),
                    'kind': 'nas',
                    'status': m.status,
                })
        except Exception:
            pass
    return libs


def _lib_root(key):
    for lib in get_libraries():
        if lib['key'] == key:
            return lib['path']
    return None


def _safe_resolve(root, rel):
    """把相对路径解析到 root 之内，防目录穿越。返回绝对路径或 None。"""
    root = os.path.realpath(root)
    target = os.path.realpath(os.path.join(root, rel or ''))
    if target == root or target.startswith(root + os.sep):
        return target
    return None


# ───────────────────────── NAS 挂载（在 Linux 服务器容器内执行） ─────────────────────────
def do_mount(m):
    mp = m.mount_path
    os.makedirs(mp, exist_ok=True)
    if m.protocol == 'smb':
        host = m.host.strip()
        share = m.share.strip().strip('/')
        src = '//' + host + '/' + share
        if m.username:
            opts = ['username=' + m.username,
                    'password=' + (m.password or ''),
                    'iocharset=utf8', 'vers=3.0', 'ro', 'soft']
        else:
            opts = ['guest', 'iocharset=utf8', 'vers=3.0', 'ro', 'soft']
        cmd = ['mount', '-t', 'cifs', src, mp, '-o', ','.join(opts)]
    else:  # nfs
        host = m.host.strip()
        share = m.share.strip().strip('/')
        src = host + ':/' + share
        cmd = ['mount', '-t', 'nfs', src, mp, '-o', 'ro,soft,timeo=30,retry=1,nofail']
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout or 'mount failed').strip())


def do_unmount(m):
    subprocess.run(['umount', '-l', m.mount_path], capture_output=True, text=True, timeout=30)
    try:
        if os.path.isdir(m.mount_path) and not os.path.ismount(m.mount_path):
            os.rmdir(m.mount_path)
    except Exception:
        pass


# ───────────────────────── 工具：范围请求流式播放 ─────────────────────────
def _parse_range(range_header, size):
    if not range_header or not range_header.startswith('bytes='):
        return None
    spec = range_header[len('bytes='):].split(',')[0].strip()
    if '-' not in spec:
        return None
    s, e = spec.split('-', 1)
    start = int(s) if s else None
    end = int(e) if e else None
    if start is None and end is None:
        return None
    if start is None:                      # 后缀形式 bytes=-N
        start = max(0, size - end)
        end = size - 1
    else:
        if end is None or end >= size:
            end = size - 1
    if start < 0 or start > end or start >= size:
        return 'invalid'
    return (start, end)


def _stream_file(fp):
    size = os.path.getsize(fp)
    mimetype = mimetypes.guess_type(fp)[0] or 'application/octet-stream'
    rng = _parse_range(request.headers.get('Range'), size)
    if rng == 'invalid':
        resp = Response(status=416)
        resp.headers['Content-Range'] = 'bytes */%d' % size
        return resp
    if rng is None:
        def gen():
            with open(fp, 'rb') as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    yield chunk
        resp = Response(gen(), mimetype=mimetype)
        resp.headers['Accept-Ranges'] = 'bytes'
        resp.headers['Content-Length'] = str(size)
        return resp
    start, end = rng
    length = end - start + 1
    def gen():
        with open(fp, 'rb') as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(65536, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk
    resp = Response(gen(), status=206, mimetype=mimetype)
    resp.headers['Content-Range'] = 'bytes %d-%d/%d' % (start, end, size)
    resp.headers['Accept-Ranges'] = 'bytes'
    resp.headers['Content-Length'] = str(length)
    return resp


# ───────────────────────── 工具：音频元数据（封面/歌词/标签） ─────────────────────────
def _extract_meta(fp):
    info = {'title': None, 'artist': None, 'album': None, 'duration': None,
            'cover': False, 'lyrics': False}
    try:
        from mutagen import File as MutagenFile
        audio = MutagenFile(fp)
        if audio is not None:
            if getattr(audio, 'info', None) and audio.info.length:
                info['duration'] = int(audio.info.length)
            try:
                if getattr(audio, 'pictures', None):
                    info['cover'] = True
                elif audio.get('APIC') or audio.get('covr'):
                    info['cover'] = True
            except Exception:
                pass
            try:
                if audio.get('USLT') or audio.get('LYRICS') or audio.get('lyrics'):
                    info['lyrics'] = True
            except Exception:
                pass
            if not info['lyrics']:
                base = os.path.splitext(fp)[0]
                info['lyrics'] = os.path.isfile(base + '.lrc') or os.path.isfile(base + '.txt')
            def get(*keys):
                for k in keys:
                    v = audio.get(k)
                    if v:
                        val = v[0] if isinstance(v, list) else v
                        try:
                            return str(val)
                        except Exception:
                            return None
                return None
            info['title'] = get('TIT2', 'title', 'TITLE')
            info['artist'] = get('TPE1', 'artist', 'ARTIST')
            info['album'] = get('TALB', 'album', 'ALBUM')
    except Exception:
        pass
    return info


def _extract_cover(fp):
    try:
        from mutagen import File as MutagenFile
        audio = MutagenFile(fp)
        if audio is None:
            return None
        pics = []
        try:
            pics = getattr(audio, 'pictures', None) or []
        except Exception:
            pass
        if not pics:
            apic = audio.get('APIC')
            if apic:
                pics = apic if isinstance(apic, list) else [apic]
        if not pics:
            covr = getattr(audio, 'covr', None)
            if covr:
                pics = covr if isinstance(covr, list) else [covr]
        if pics:
            data = pics[0].data if hasattr(pics[0], 'data') else pics[0]
            return data
    except Exception:
        return None
    return None


def _extract_lyrics(fp):
    try:
        from mutagen import File as MutagenFile
        audio = MutagenFile(fp)
        if audio is not None:
            uslt = audio.get('USLT')
            if uslt:
                txt = uslt.text if hasattr(uslt, 'text') else uslt
                if isinstance(txt, list):
                    txt = txt[0]
                if txt:
                    return str(txt)
            for tag in ('LYRICS', 'lyrics'):
                v = audio.get(tag)
                if v:
                    return str(v[0])
    except Exception:
        pass
    base = os.path.splitext(fp)[0]
    for ext in ('.lrc', '.txt'):
        p = base + ext
        if os.path.isfile(p):
            try:
                with open(p, encoding='utf-8', errors='ignore') as f:
                    return f.read()
            except Exception:
                pass
    return None


def _friendly_name(fp):
    return os.path.splitext(os.path.basename(fp))[0]


# ───────────────────────── 服务器端播放（mpv，声音从服务器出） ─────────────────────────
MPV_SOCK = '/tmp/mpv-music.sock'


class ServerPlayer:
    """用 mpv（带 IPC socket）在服务器本机出声播放。

    适用场景：服务器接了功放/音箱（全屋共用一路），希望声音从服务器出来，
    而非仅从打开页面的客户端出声。前端通过 /player/* 接口控制，不依赖浏览器。
    """

    def __init__(self):
        self.lock = threading.Lock()
        self.proc = None
        self._rid = 0
        self._launch_dev = None
        self.state = {
            'active': False, 'kind': None, 'name': None, 'url': None,
            'paused': False, 'position': 0.0, 'duration': 0.0,
            'volume': 80, 'device': 'default', 'error': ''
        }

    @staticmethod
    def _mpv_available():
        return bool(shutil.which('mpv'))

    def _ensure(self, device=None):
        # 已运行且 socket 存在
        if self.proc and self.proc.poll() is None and os.path.exists(MPV_SOCK):
            if device and device != self._launch_dev:
                self.stop()           # 设备变了，重启以应用新 audio-device
            else:
                return True
        if device:
            self._launch_dev = device
        if os.path.exists(MPV_SOCK):
            try:
                os.unlink(MPV_SOCK)
            except Exception:
                pass
        if not self._mpv_available():
            self.state['error'] = '服务器未安装 mpv，无法在服务器端播放（请确认镜像已安装 mpv）'
            return False
        dev = device or self._launch_dev or 'default'
        cmd = ['mpv', '--no-terminal', '--no-video', '--idle=yes',
               '--input-ipc-server=' + MPV_SOCK, '--audio-device=' + dev]
        try:
            self.proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                         stderr=subprocess.DEVNULL)
        except Exception as e:
            self.state['error'] = '启动 mpv 失败：' + str(e)
            return False
        for _ in range(50):                      # 等待 IPC socket 就绪（最多 5s）
            if os.path.exists(MPV_SOCK):
                try:
                    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    s.settimeout(0.5)
                    s.connect(MPV_SOCK)
                    s.close()
                    return True
                except Exception:
                    pass
            time.sleep(0.1)
        self.state['error'] = 'mpv 启动超时（可能服务器缺少音频设备，或 /dev/snd 未透传进容器）'
        return False

    def _ipc(self, command, timeout=2.0):
        s = None
        try:
            with self.lock:
                s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                s.settimeout(timeout)
                s.connect(MPV_SOCK)
                self._rid += 1
                msg = json.dumps({'command': command, 'request_id': self._rid}) + '\n'
                s.sendall(msg.encode())
                buf = ''
                while True:
                    data = s.recv(4096).decode(errors='ignore')
                    if not data:
                        break
                    buf += data
                    while '\n' in buf:
                        line, buf = buf.split('\n', 1)
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            obj = json.loads(line)
                        except Exception:
                            continue
                        if obj.get('request_id') == self._rid:   # 忽略事件等其它消息
                            return obj
                return {'error': 'no-response'}
        except Exception as e:
            return {'error': str(e)}
        finally:
            if s is not None:
                try:
                    s.close()
                except Exception:
                    pass

    def play(self, url, name, kind, device=None):
        if device:
            self.state['device'] = device
            self._launch_dev = device
        if not self._ensure(device):
            return False
        r = self._ipc(['loadfile', url, 'replace'])
        if r.get('error') not in (None, 'success'):
            self.state['error'] = 'loadfile 失败：' + str(r.get('error'))
            return False
        self.state.update(active=True, kind=kind, name=name, url=url,
                          paused=False, position=0.0, duration=0.0, error='')
        if self.state['volume'] != 80:
            self._ipc(['set_property', 'volume', float(self.state['volume'])], timeout=1)
        return True

    def pause(self, on):
        r = self._ipc(['set_property', 'pause', bool(on)])
        if r.get('error') in (None, 'success'):
            self.state['paused'] = bool(on)
        return r

    def stop(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except Exception:
                pass
            try:
                self.proc.wait(timeout=3)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
        self.proc = None
        self.state.update(active=False, paused=False, position=0.0, duration=0.0)

    def volume(self, v):
        v = max(0, min(100, int(v)))
        self.state['volume'] = v
        self._ipc(['set_property', 'volume', float(v)], timeout=1)
        return v

    def seek(self, sec):
        self._ipc(['seek', float(sec), 'absolute'], timeout=1)

    def status(self):
        if self.proc and self.proc.poll() is None and os.path.exists(MPV_SOCK):
            for prop, key in (('time-pos', 'position'), ('duration', 'duration'),
                              ('pause', 'paused'), ('volume', 'volume')):
                r = self._ipc(['get_property', prop], timeout=1)
                if r.get('error') in (None, 'success') and 'data' in r:
                    self.state[key] = r['data']
        elif self.state['active'] and (not self.proc or self.proc.poll() is not None):
            self.state['active'] = False
            self.state['error'] = '播放进程已退出'
        return dict(self.state)


player = ServerPlayer()


# ───────────────────────── 全局播放互斥（服务器 vs 客户端集群） ─────────────────────────
# 规则（按用户要求）：
#  - 多个客户端（浏览器标签 / 设备）可同时在各自设备上播放，互不限制；
#  - 但「服务器音箱」播放 与 任何客户端播放 不能同时出现（互斥）；
#  - 冲突时「服务器优先」：服务器在放，客户端发起的播放会被静音（不让客户端抢走全屋声音）。
# 实现：维护一个 mode（server / client / None）与一组活跃 client_id（心跳维护）。
_gstate = {
    'server_item': None,   # 服务器当前播放项 {type, name}
    'clients': {},         # client_id -> {'active': bool, 'ts': float}
}
_glock = threading.Lock()
HEARTBEAT_TTL = 12  # 秒：活跃客户端超过此时长无心跳即视为离线，自动清理


def _prune_clients():
    now = time.time()
    dead = [cid for cid, c in _gstate['clients'].items()
            if now - c['ts'] > HEARTBEAT_TTL]
    for cid in dead:
        _gstate['clients'].pop(cid, None)


def client_active_count():
    _prune_clients()
    return sum(1 for c in _gstate['clients'].values() if c['active'])


def report_client(client_id, active):
    """客户端心跳：上报本客户端是否正在播放（active）。服务器优先：
    即使客户端上报 active=True，只要服务器正在播放，也不会停掉服务器
    （全局状态会令该客户端静音）。返回全局状态。"""
    with _glock:
        _prune_clients()
        c = _gstate['clients'].get(client_id)
        if c is None:
            c = {'active': bool(active), 'ts': time.time()}
            _gstate['clients'][client_id] = c
        else:
            c['active'] = bool(active)
            c['ts'] = time.time()
        return global_state()


def set_server_item(item):
    with _glock:
        _gstate['server_item'] = item


def clear_server_item():
    with _glock:
        _gstate['server_item'] = None


def global_state():
    with _glock:
        _prune_clients()
        st = player.status()
        server_active = bool(st.get('active'))
        clients = client_active_count()
        if server_active:
            mode = 'server'
            client_must_mute = True     # 服务器在放 → 所有客户端必须静音
        elif clients > 0:
            mode = 'client'
            client_must_mute = False
        else:
            mode = None
            client_must_mute = False
        return {
            'mode': mode,
            'server_active': server_active,
            'server_paused': st.get('paused', False),
            'server_kind': st.get('kind'),
            'server_name': (_gstate['server_item'] or {}).get('name'),
            'server_type': (_gstate['server_item'] or {}).get('type'),
            'position': st.get('position', 0),
            'duration': st.get('duration', 0),
            'device': st.get('device'),
            'error': st.get('error'),
            'clients_active': clients,
            'client_must_mute': client_must_mute,
        }


def list_audio_devices():
    devs = [{'id': 'default', 'name': '默认输出'}]
    try:
        out = subprocess.run(['mpv', '--audio-device=help'],
                             capture_output=True, text=True, timeout=5).stdout
        for line in out.splitlines():
            m = re.search(r"'(alsa/[^']+)'\s*\(([^)]*)\)", line)
            if m:
                devs.append({'id': m.group(1), 'name': m.group(2).strip()})
        if len(devs) > 1:
            return devs
    except Exception:
        pass
    try:
        out = subprocess.run(['aplay', '-L'], capture_output=True,
                             text=True, timeout=5).stdout
        for line in out.splitlines():
            if line and not line.startswith(' ') and line != 'null':
                devs.append({'id': 'alsa/' + line, 'name': line})
    except Exception:
        pass
    return devs


# ───────────────────────── 通用 ─────────────────────────
@app.after_request
def _cors(resp):
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Access-Control-Allow-Methods'] = 'GET,POST,DELETE,OPTIONS'
    resp.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return resp


@app.route('/health')
def health():
    return jsonify(ok=True, libraries=get_libraries())


# ───────────────────────── 电台（保留） ─────────────────────────
@app.route('/stations', methods=['GET'])
def list_stations():
    rows = Station.query.order_by(Station.id).all()
    return jsonify([
        {'id': r.id, 'name': r.name, 'url': r.url, 'genre': r.genre, 'custom': r.custom}
        for r in rows
    ])


@app.route('/stations', methods=['POST'])
def add_station():
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get('name') or '').strip()
    url = (data.get('url') or '').strip()
    genre = (data.get('genre') or '自定义').strip()
    if not name or not url:
        return jsonify(error='name and url required'), 400
    s = Station(name=name, url=url, genre=genre, custom=True)
    db.session.add(s)
    db.session.commit()
    return jsonify({'id': s.id, 'name': s.name, 'url': s.url, 'genre': s.genre, 'custom': s.custom}), 201


@app.route('/stations/<int:sid>', methods=['DELETE'])
def del_station(sid):
    s = Station.query.get(sid)
    if not s:
        return jsonify(error='not found'), 404
    db.session.delete(s)
    db.session.commit()
    return jsonify(ok=True)


# ───────────────────────── NAS 音乐源管理（Web 页面挂载） ─────────────────────────
@app.route('/nas', methods=['GET'])
def list_nas():
    rows = NasMount.query.order_by(NasMount.id).all()
    return jsonify([
        {'name': r.name, 'protocol': r.protocol, 'host': r.host, 'share': r.share,
         'username': r.username, 'mount_path': r.mount_path, 'status': r.status, 'error': r.error}
        for r in rows
    ])


@app.route('/nas/mount', methods=['POST'])
def mount_nas():
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get('name') or '').strip()
    protocol = (data.get('protocol') or 'smb').strip().lower()
    host = (data.get('host') or '').strip()
    share = (data.get('share') or '').strip()
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    if not name or not host or not share:
        return jsonify(error='name, host, share required'), 400
    if protocol not in ('smb', 'nfs'):
        return jsonify(error='protocol must be smb or nfs'), 400
    if not _validate_host(host) or not _validate_share(share):
        return jsonify(error='invalid host or share'), 400
    safe = _safe_mount_name(name)
    mp = os.path.join(NAS_BASE, 'nas-' + safe)
    m = NasMount.query.filter_by(name=name).first()
    if not m:
        m = NasMount(name=name)
    m.protocol = protocol
    m.host = host
    m.share = share
    m.username = username
    m.password = password
    m.mount_path = mp
    m.status = 'mounting'
    db.session.add(m)
    db.session.commit()
    try:
        do_mount(m)
        m.status = 'mounted'
        m.error = ''
    except Exception as e:
        m.status = 'error'
        m.error = str(e)[:300]
    db.session.commit()
    return jsonify({'name': m.name, 'status': m.status, 'error': m.error, 'mount_path': m.mount_path}), 200


@app.route('/nas/unmount', methods=['POST'])
def unmount_nas():
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get('name') or '').strip()
    m = NasMount.query.filter_by(name=name).first()
    if not m:
        return jsonify(error='not found'), 404
    try:
        do_unmount(m)
        m.status = 'unmounted'
        m.error = ''
    except Exception as e:
        m.error = str(e)[:300]
    db.session.commit()
    return jsonify({'name': m.name, 'status': m.status, 'error': m.error})


@app.route('/nas/<name>', methods=['DELETE'])
def del_nas(name):
    m = NasMount.query.filter_by(name=name).first()
    if not m:
        return jsonify(error='not found'), 404
    try:
        do_unmount(m)
    except Exception:
        pass
    db.session.delete(m)
    db.session.commit()
    return jsonify(ok=True)


# ───────────────────────── 音乐库 ─────────────────────────
@app.route('/libraries')
def libraries():
    return jsonify(get_libraries())


@app.route('/browse')
def browse():
    lib_key = request.args.get('lib', '')
    rel = request.args.get('path', '')
    root = _lib_root(lib_key)
    if not root:
        return jsonify(error='unknown library'), 400
    target = _safe_resolve(root, rel)
    if target is None or not os.path.isdir(target):
        return jsonify(error='invalid path'), 400
    dirs, files = [], []
    try:
        names = sorted(os.listdir(target))
    except Exception:
        names = []
    for name in names:
        fp = os.path.join(target, name)
        if os.path.isdir(fp):
            dirs.append({'name': name, 'is_dir': True})
        else:
            ext = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
            if ext in AUDIO_EXTS:
                files.append({'name': name, 'is_dir': False,
                              'size': os.path.getsize(fp), 'ext': ext})
    return jsonify({'lib': lib_key, 'path': rel, 'dirs': dirs, 'files': files})


@app.route('/media')
def media():
    lib_key = request.args.get('lib', '')
    rel = request.args.get('path', '')
    root = _lib_root(lib_key)
    if not root:
        return jsonify(error='unknown library'), 400
    target = _safe_resolve(root, rel)
    if target is None or not os.path.isfile(target):
        abort(404)
    return _stream_file(target)


@app.route('/track/meta')
def track_meta():
    lib_key = request.args.get('lib', '')
    rel = request.args.get('path', '')
    root = _lib_root(lib_key)
    if not root:
        return jsonify(error='unknown library'), 400
    target = _safe_resolve(root, rel)
    if target is None or not os.path.isfile(target):
        abort(404)
    info = _extract_meta(target)
    if not info['title']:
        info['title'] = _friendly_name(target)
    return jsonify(info)


@app.route('/track/cover')
def track_cover():
    lib_key = request.args.get('lib', '')
    rel = request.args.get('path', '')
    root = _lib_root(lib_key)
    if not root:
        abort(400)
    target = _safe_resolve(root, rel)
    if target is None or not os.path.isfile(target):
        abort(404)
    data = _extract_cover(target)
    if not data:
        abort(404)
    return Response(data, mimetype='image/jpeg')


@app.route('/track/lyrics')
def track_lyrics():
    lib_key = request.args.get('lib', '')
    rel = request.args.get('path', '')
    root = _lib_root(lib_key)
    if not root:
        abort(400)
    target = _safe_resolve(root, rel)
    if target is None or not os.path.isfile(target):
        abort(404)
    text = _extract_lyrics(target)
    if not text:
        abort(404)
    return Response(text, mimetype='text/plain; charset=utf-8')


# ───────────────────────── 收藏 ─────────────────────────
@app.route('/favorites', methods=['GET'])
def list_fav():
    rows = Favorite.query.order_by(Favorite.added.desc()).all()
    return jsonify([
        {'id': r.id, 'source': r.source, 'lib_key': r.lib_key, 'path': r.path,
         'title': r.title, 'artist': r.artist, 'album': r.album}
        for r in rows
    ])


@app.route('/favorites', methods=['POST'])
def add_fav():
    data = request.get_json(force=True, silent=True) or {}
    source = (data.get('source') or '').strip()
    lib_key = (data.get('lib_key') or '').strip()
    path = (data.get('path') or '').strip()
    if not source or not path:
        return jsonify(error='source and path required'), 400
    exists = Favorite.query.filter_by(source=source, lib_key=lib_key, path=path).first()
    if exists:
        return jsonify({'id': exists.id, 'title': exists.title, 'artist': exists.artist,
                        'album': exists.album, 'source': source, 'lib_key': lib_key,
                        'path': path, 'already': True})
    f = Favorite(source=source, lib_key=lib_key, path=path,
                 title=(data.get('title') or '').strip(),
                 artist=(data.get('artist') or '').strip(),
                 album=(data.get('album') or '').strip())
    db.session.add(f)
    db.session.commit()
    return jsonify({'id': f.id, 'title': f.title, 'artist': f.artist, 'album': f.album,
                    'source': source, 'lib_key': lib_key, 'path': path}), 201


@app.route('/favorites/<int:fid>', methods=['DELETE'])
def del_fav(fid):
    f = Favorite.query.get(fid)
    if not f:
        return jsonify(error='not found'), 404
    db.session.delete(f)
    db.session.commit()
    return jsonify(ok=True)


# ───────────────────────── 服务器端播放 API ─────────────────────────
@app.route('/player/devices')
def player_devices():
    return jsonify(list_audio_devices())


@app.route('/player/status')
def player_status():
    return jsonify(player.status())


@app.route('/player/play', methods=['POST'])
def player_play():
    data = request.get_json(force=True, silent=True) or {}
    kind = data.get('kind') or 'radio'
    name = data.get('name') or '未知'
    device = (data.get('device') or '').strip() or None
    if kind == 'radio':
        url = (data.get('url') or '').strip()
        if not url:
            return jsonify(error='url required'), 400
    else:  # file：解析到服务器本地/挂载目录的绝对路径，直接交给 mpv 播放
        lib_key = (data.get('lib_key') or '').strip()
        path = (data.get('path') or '').strip()
        root = _lib_root(lib_key)
        if not root:
            return jsonify(error='unknown library'), 400
        target = _safe_resolve(root, path)
        if target is None or not os.path.isfile(target):
            return jsonify(error='file not found'), 404
        url = target
    set_server_item({'type': kind, 'name': name})
    ok = player.play(url, name, kind, device)
    if not ok:
        clear_server_item()
        return jsonify(error=player.state.get('error') or 'play failed'), 500
    return jsonify(global_state())


@app.route('/player/pause', methods=['POST'])
def player_pause():
    player.pause(True)
    return jsonify(player.status())


@app.route('/player/resume', methods=['POST'])
def player_resume():
    player.pause(False)
    return jsonify(player.status())


@app.route('/player/stop', methods=['POST'])
def player_stop():
    player.stop()
    clear_server_item()
    return jsonify(global_state())


# 全局播放互斥状态：客户端通过 POST 上报自身是否在播放（心跳），并取回全局状态。
# GET 仅取状态（可带 client_id 刷新心跳时间戳）。
@app.route('/player/global', methods=['GET', 'POST'])
def player_global():
    if request.method == 'POST':
        data = request.get_json(force=True, silent=True) or {}
        cid = (data.get('client_id') or '').strip()
        active = bool(data.get('active', False))
        if cid:
            return jsonify(report_client(cid, active))
        return jsonify(global_state())
    cid = request.args.get('client_id')
    if cid:                       # GET 也顺带刷新心跳时间戳（若存在）
        with _glock:
            c = _gstate['clients'].get(cid)
            if c is not None:
                c['ts'] = time.time()
    return jsonify(global_state())


@app.route('/player/volume', methods=['POST'])
def player_volume():
    data = request.get_json(force=True, silent=True) or {}
    player.volume(data.get('value', 80))
    return jsonify(player.status())


@app.route('/player/seek', methods=['POST'])
def player_seek():
    data = request.get_json(force=True, silent=True) or {}
    player.seek(data.get('seconds', 0))
    return jsonify(player.status())


@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def _catch(path):
    return jsonify(error='not found'), 404


# ───────────────────────── 启动初始化 ─────────────────────────
if HAVE_SQLA:
    with app.app_context():
        db.create_all()
        if Station.query.count() == 0:
            for n, u, g in DEFAULTS:
                db.session.add(Station(name=n, url=u, genre=g, custom=False))
            db.session.commit()
        # 启动时自动重新挂载已保存的 NAS 音乐源（容器重启后挂载命名空间会丢失）
        try:
            for m in NasMount.query.all():
                try:
                    if not os.path.ismount(m.mount_path):
                        do_mount(m)
                        m.status = 'mounted'
                        m.error = ''
                    else:
                        m.status = 'mounted'
                except Exception as e:
                    m.status = 'error'
                    m.error = str(e)[:300]
                db.session.commit()
        except Exception:
            pass


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
