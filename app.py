import os
import uuid
import base64
import subprocess
import tempfile
import time
import requests
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

SESSION_TTL_SECONDS = int(os.environ.get('SESSION_TTL_SECONDS', '86400'))
DEFAULT_TELEGRAM_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '').strip()
DEFAULT_TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '').strip()

# ─────────────────────────────────────────────────────────────
# Sesiones compartidas (ADMIN/CLIENTE) – en memoria
# Nota: si el servicio se reinicia, se pierden. (Sin caducidad por petición)
# ─────────────────────────────────────────────────────────────
SESSIONS = {}  # sid -> {"ver": int, "data": dict, "created_at": int, "updated_at": int}

def _sid_ok(sid: str) -> bool:
    return isinstance(sid, str) and 1 <= len(sid) <= 64

def _prune_sessions() -> None:
    if SESSION_TTL_SECONDS <= 0:
        return

    now = int(time.time())
    expired = [
        sid for sid, cur in SESSIONS.items()
        if now - int(cur.get('updated_at', cur.get('created_at', now))) > SESSION_TTL_SECONDS
    ]
    for sid in expired:
        SESSIONS.pop(sid, None)

def _decode_base64(value: str) -> bytes:
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Contenido base64 invalido')
    return base64.b64decode(value, validate=True)

def _telegram_request(url: str, **kwargs):
    response = requests.post(url, timeout=kwargs.pop('timeout', 15), **kwargs)
    try:
        payload = response.json()
    except ValueError:
        payload = None

    if response.status_code >= 400:
        detail = payload.get('description') if isinstance(payload, dict) else response.text
        raise RuntimeError(detail or f'HTTP {response.status_code}')

    if isinstance(payload, dict) and not payload.get('ok', True):
        raise RuntimeError(payload.get('description') or 'Telegram devolvio un error')

    return payload

@app.route('/', methods=['GET'])
def index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/config', methods=['GET'])
def config():
    return jsonify({
        'ok': True,
        'telegram_enabled': bool(DEFAULT_TELEGRAM_TOKEN and DEFAULT_TELEGRAM_CHAT_ID),
        'session_ttl_seconds': SESSION_TTL_SECONDS,
    })

@app.route('/session/save', methods=['POST'])
def session_save():
    try:
        _prune_sessions()
        payload = request.get_json(silent=True) or {}
        sid = payload.get('sid')
        data = payload.get('data')
        base_ver = payload.get('base_ver')
        if not _sid_ok(sid):
            return jsonify({'ok': False, 'error': 'sid inválido'}), 400
        if not isinstance(data, dict):
            return jsonify({'ok': False, 'error': 'data inválido'}), 400

        now = int(time.time())
        cur = SESSIONS.get(sid, {'ver': 0, 'data': {}, 'created_at': now, 'updated_at': now})
        cur_ver = int(cur.get('ver', 0))
        # Si el cliente intenta guardar sobre una versión vieja, igual aceptamos (last-write-wins)
        new_ver = cur_ver + 1
        SESSIONS[sid] = {
            'ver': new_ver,
            'data': data,
            'created_at': int(cur.get('created_at', now)),
            'updated_at': now,
        }
        return jsonify({'ok': True, 'sid': sid, 'ver': new_ver, 'updated_at': now})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/session/get', methods=['GET'])
def session_get():
    try:
        _prune_sessions()
        sid = request.args.get('sid', '')
        if not _sid_ok(sid):
            return jsonify({'ok': False, 'error': 'sid inválido'}), 400
        cur = SESSIONS.get(sid)
        if not cur:
            return jsonify({'ok': True, 'sid': sid, 'ver': 0, 'data': None})
        return jsonify({
            'ok': True,
            'sid': sid,
            'ver': int(cur.get('ver', 0)),
            'updated_at': int(cur.get('updated_at', 0)),
            'data': cur.get('data'),
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/session/list', methods=['GET'])
def session_list():
    try:
        _prune_sessions()
        try:
            limit = int(request.args.get('limit', '15'))
        except Exception:
            limit = 15
        if limit < 1:
            limit = 1
        if limit > 50:
            limit = 50

        items = []
        for sid, cur in SESSIONS.items():
            try:
                data = cur.get('data') or {}
                cn = (data.get('cn') or '').strip()
                # Solo listar sesiones que ya tienen nombre (para que el cliente vea "Nombre", no códigos)
                if not cn:
                    continue
                items.append({
                    'sid': sid,
                    'cn': cn,
                    'ver': int(cur.get('ver', 0)),
                    'updated_at': int(cur.get('updated_at', 0)),
                    'created_at': int(cur.get('created_at', 0)),
                })
            except Exception:
                continue
        items.sort(key=lambda x: x.get('updated_at', 0), reverse=True)
        return jsonify({'ok': True, 'sessions': items[:limit]})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/session/clear', methods=['POST'])
def session_clear():
    try:
        _prune_sessions()
        payload = request.get_json(silent=True) or {}
        sid = payload.get('sid')
        if not _sid_ok(sid):
            return jsonify({'ok': False, 'error': 'sid inválido'}), 400
        SESSIONS.pop(sid, None)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    _prune_sessions()
    return jsonify({'status': 'ok', 'sessions': len(SESSIONS)})

@app.route('/convert', methods=['POST'])
def convert():
    try:
        data = request.get_json(silent=True) or {}
        if not data or 'xlsx_b64' not in data:
            return jsonify({'error': 'Falta el campo xlsx_b64'}), 400

        xlsx_bytes = _decode_base64(data['xlsx_b64'])

        with tempfile.TemporaryDirectory(prefix='ic-pdf-') as tmp_dir:
            tmp_id = str(uuid.uuid4())
            xlsx_path = os.path.join(tmp_dir, f'{tmp_id}.xlsx')
            pdf_path = os.path.join(tmp_dir, f'{tmp_id}.pdf')

            with open(xlsx_path, 'wb') as file_handle:
                file_handle.write(xlsx_bytes)

            result = subprocess.run(
                [
                    'libreoffice',
                    '--headless',
                    '--norestore',
                    '--convert-to',
                    'pdf',
                    '--outdir',
                    tmp_dir,
                    xlsx_path,
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode != 0 or not os.path.exists(pdf_path):
                return jsonify({
                    'error': 'Error al convertir',
                    'detalle': (result.stderr or result.stdout or 'LibreOffice no genero el PDF').strip(),
                }), 500

            with open(pdf_path, 'rb') as file_handle:
                pdf_b64 = base64.b64encode(file_handle.read()).decode('ascii')

        return jsonify({'pdf_b64': pdf_b64})

    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/telegram', methods=['POST'])
def telegram():
    try:
        data = request.get_json(silent=True) or {}
        token = (data.get('token') or DEFAULT_TELEGRAM_TOKEN).strip()
        chat_id = str(data.get('chat_id') or DEFAULT_TELEGRAM_CHAT_ID).strip()
        if not token or not chat_id:
            return jsonify({'ok': False, 'error': 'Faltan token o chat_id'}), 400

        text = str(data.get('text', '')).strip()
        pdf_b64 = data.get('pdf_b64')
        filename = str(data.get('filename', 'informe.pdf')).strip() or 'informe.pdf'

        _telegram_request(
            f'https://api.telegram.org/bot{token}/sendMessage',
            json={'chat_id': chat_id, 'text': text},
            timeout=10,
        )

        if pdf_b64 and filename:
            pdf_bytes = _decode_base64(pdf_b64)
            files = {'document': (filename, pdf_bytes, 'application/pdf')}
            _telegram_request(
                f'https://api.telegram.org/bot{token}/sendDocument',
                data={'chat_id': chat_id, 'caption': text[:200]},
                files=files,
                timeout=30,
            )

        return jsonify({'ok': True})
    except ValueError as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
