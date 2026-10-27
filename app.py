import json
import threading
import time

from flask import Flask, jsonify, render_template, request
from flask_mqtt import Mqtt

from config import Config
from extensions import db
from models import Leitura

app = Flask(__name__,template_folder='views', static_folder='static')
app.config.from_object(Config)

db.init_app(app)
with app.app_context():
    db.create_all()

mqtt = Mqtt()
mqtt.init_app(app)

PREFIXO = app.config['MQTT_TOPIC_PREFIX']
MOTORES = {'bb', 'be'}
MAX_PONTOS_API = 1000

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
    leitura = Leitura(
    motor=motor,
    t=ts if ts > 1.6e9 else agora,
    ts_dispositivo=ts,
    recebido_em=agora,
    rms=rms,
    pico=pico,
    rpm=rpm,
)

    with app.app_context():
        try:
            db.session.add(leitura)
            db.session.commit()
        except Exception:
            db.session.rollback()
            app.logger.exception('Falha ao gravar leitura')

def reduzir(pontos, minutos, limite=MAX_PONTOS_API):
    """Se houver pontos demais, agrupa em intervalos de tempo iguais (média; pico = máximo)."""
    if len(pontos) <= limite:
        return pontos
 
    largura = (minutos * 60) / limite
    baldes = {}
    for p in pontos:
        baldes.setdefault(int(p['t'] // largura), []).append(p)
 
    saida = []
    for k in sorted(baldes):
        g = baldes[k]
        n = len(g)
        picos = [p['pico'] for p in g if p['pico'] is not None]
        saida.append({
            'motor': g[0]['motor'],
            't': sum(p['t'] for p in g) / n,
            'recebido_em': max(p['recebido_em'] for p in g),
            'rms': sum(p['rms'] for p in g) / n,
            'pico': max(picos) if picos else None,
            'rpm': sum(p['rpm'] for p in g) / n,
        })
    return saida

@app.route('/')
def index():
    return render_template('dashboard.html')

@app.route('/api/ultimos')
def api_ultimos():
    saida = {}
    for m in MOTORES:
        leitura = db.session.scalars(
            db.select(Leitura).where(Leitura.motor == m).order_by(Leitura.id.desc()).limit(1)
        ).first()
        saida[m] = leitura.to_dict() if leitura else None
    return jsonify(saida)

@app.route('/api/historico')
def api_historico():
    minutos = min(max(request.args.get('minutos', 10, type=int), 1), 1440)
    agora = time.time()
    desde = agora - minutos * 60
 
    saida = {'agora': agora}
    for m in MOTORES:
        leituras = db.session.scalars(
            db.select(Leitura)
            .where(Leitura.motor == m, Leitura.t >= desde)
            .order_by(Leitura.t)
        ).all()
        saida[m] = reduzir([l.to_dict() for l in leituras], minutos)
    return jsonify(saida)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)