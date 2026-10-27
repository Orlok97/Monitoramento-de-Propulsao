import json
import threading
import time

from flask import Flask, jsonify, render_template
from flask_mqtt import Mqtt

from config import Config

app = Flask(__name__,template_folder='views', static_folder='static')
app.config.from_object(Config)

mqtt = Mqtt()
mqtt.init_app(app)

PREFIXO = app.config['MQTT_TOPIC_PREFIX']
MOTORES = {'bb', 'be'}

lock = threading.Lock()
ultimos = {'bb': None, 'be': None}

@mqtt.on_connect()
def handle_connect(client, userdata, flags, rc):
    if rc == 0:
        print('MQTT conectado')
        mqtt.subscribe(f'{PREFIXO}/+/dados')
    else:
        print('Falha na conexão MQTT, rc =', rc)


@mqtt.on_message()
def handle_message(client, userdata, message):
    partes = message.topic.split('/')
    if len(partes) != 3 or partes[0] != PREFIXO or partes[2] != 'dados' or partes[1] not in MOTORES:
        return
    motor = partes[1]

    try:
        d = json.loads(message.payload.decode())
        rms, rpm = float(d['rms']), float(d['rpm'])
        if not (0 <= rms < 1000 and 0 <= rpm < 10000):
            return
        pico = d.get('pico')
        ts = float(d.get('ts', 0) or 0)
    except (json.JSONDecodeError, UnicodeDecodeError, KeyError, TypeError, ValueError):
        return

    agora = time.time()
    leitura = {
        'rms': rms,
        'pico': float(pico) if pico is not None else None,
        'rpm': rpm,
        'ts_dispositivo': ts,
        'recebido_em': agora,
        't': ts if ts > 1.6e9 else agora,
    }
    with lock:
        ultimos[motor] = leitura


@app.route('/')
def index():
    return render_template('dashboard.html')

@app.route('/api/ultimos')
def api_ultimos():
    with lock:
        return jsonify(ultimos)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)