import os
import uuid
import base64
import subprocess
import tempfile
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})

@app.route('/convert', methods=['POST'])
def convert():
    try:
        data = request.get_json()
        if not data or 'xlsx_b64' not in data:
            return jsonify({'error': 'Falta el campo xlsx_b64'}), 400

        xlsx_bytes = base64.b64decode(data['xlsx_b64'])

        tmp_id = str(uuid.uuid4())
        xlsx_path = f'/tmp/{tmp_id}.xlsx'
        pdf_path  = f'/tmp/{tmp_id}.pdf'

        with open(xlsx_path, 'wb') as f:
            f.write(xlsx_bytes)

        result = subprocess.run(
            ['libreoffice', '--headless', '--norestore',
             '--convert-to', 'pdf',
             '--outdir', '/tmp',
             xlsx_path],
            capture_output=True, text=True, timeout=60
        )

        if result.returncode != 0 or not os.path.exists(pdf_path):
            os.remove(xlsx_path)
            return jsonify({
                'error': 'Error al convertir',
                'detalle': result.stderr
            }), 500

        with open(pdf_path, 'rb') as f:
            pdf_b64 = base64.b64encode(f.read()).decode('ascii')

        os.remove(xlsx_path)
        os.remove(pdf_path)

        return jsonify({'pdf_b64': pdf_b64})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/telegram', methods=['POST'])
def telegram():
    try:
        data = request.get_json()
        if not data or not data.get('token') or not data.get('chat_id'):
            return jsonify({'ok': False, 'error': 'Faltan token o chat_id'}), 400

        token   = data['token']
        chat_id = data['chat_id']
        text    = data.get('text', '')
        pdf_b64 = data.get('pdf_b64')
        filename = data.get('filename', 'informe.pdf')

        # 1) Enviar mensaje de texto
        requests.post(
            f'https://api.telegram.org/bot{token}/sendMessage',
            json={'chat_id': chat_id, 'text': text},
            timeout=10
        )

        # 2) Enviar PDF si viene
        if pdf_b64 and filename:
            pdf_bytes = base64.b64decode(pdf_b64)
            files = {'document': (filename, pdf_bytes, 'application/pdf')}
            requests.post(
                f'https://api.telegram.org/bot{token}/sendDocument',
                data={'chat_id': chat_id, 'caption': text[:200]},
                files=files,
                timeout=30
            )

        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
