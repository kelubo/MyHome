import os
import json

from flask import Flask, jsonify, request, abort

app = Flask(__name__)
# apps.json 的实际路径由 docker-compose 注入（挂载仓库根的 apps.json 为可读写）
APP_JSON = os.environ.get('APP_JSON', './apps.json')


def load():
    try:
        with open(APP_JSON, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {'apps': []}


def save(data):
    tmp = APP_JSON + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, APP_JSON)


@app.after_request
def _cors(resp):
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Access-Control-Allow-Methods'] = 'GET,PUT,OPTIONS'
    resp.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return resp


@app.route('/health')
def health():
    return jsonify(ok=True)


@app.route('/apps', methods=['GET'])
def get_apps():
    data = load()
    apps = data.get('apps', [])
    for a in apps:
        a.setdefault('enabled', True)
    return jsonify(apps)


@app.route('/apps/<app_id>/enabled', methods=['PUT'])
def set_enabled(app_id):
    body = request.get_json(force=True, silent=True) or {}
    val = bool(body.get('enabled', True))
    data = load()
    apps = data.get('apps', [])
    found = False
    for a in apps:
        if a.get('id') == app_id:
            a['enabled'] = val
            found = True
            break
    if not found:
        abort(404)
    save(data)
    return jsonify(ok=True, id=app_id, enabled=val)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
