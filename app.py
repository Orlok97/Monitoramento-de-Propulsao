import json
import threading
import time

from flask import Flask, jsonify, render_template, request
from flask_mqtt import Mqtt

from config import Config
from extensions import db
from models import Leitura

app = Flask(__name__, template_folder='views', static_folder='static')
app.config.from_object(Config)

db.init_app(app)
with app.app_context():
    db.create_all()
    # Migração simples e compatível com o SQLite já existente.
    # create_all() não acrescenta colunas a tabelas antigas.
    from sqlalchemy import inspect
    colunas = {c['name'] for c in inspect(db.engine).get_columns('leituras')}
    novas = {
        'rx': 'FLOAT', 'ry': 'FLOAT', 'rz': 'FLOAT',
        'mpu_ok': 'BOOLEAN NOT NULL DEFAULT 1',
        'mpu_erros': 'INTEGER',
        'pz_rms': 'FLOAT', 'pz_pico': 'FLOAT', 'pz_crista': 'FLOAT',
        'pz_dc': 'FLOAT', 'pz_fs': 'INTEGER', 'pz_clip': 'INTEGER',
        'pz_ok': 'BOOLEAN NOT NULL DEFAULT 0',
    }
    for nome, tipo in novas.items():
        if nome not in colunas:
            db.session.execute(db.text(f'ALTER TABLE leituras ADD COLUMN {nome} {tipo}'))
    db.session.commit()

mqtt = Mqtt()
mqtt.init_app(app)

PREFIXO = app.config['MQTT_TOPIC_PREFIX']
MOTORES = ('bb', 'be')
TIPOS_ROTACAO = ('rotacao', 'rpm')  # rpm mantido para compatibilidade com versões anteriores
MAX_PONTOS_API = 1000
RPM_MAX_IDADE_S = 3.0

# O ESP32 de rotação publica dois tópicos independentes:
# <prefixo>/bb/rotacao e <prefixo>/be/rotacao.
rpm_atual = {m: None for m in MOTORES}
rpm_lock = threading.Lock()


def numero(dados, chave, padrao=None):
    valor = dados.get(chave, padrao)
    if valor is None:
        return None
    valor = float(valor)
    if not (-1e12 < valor < 1e12):
        raise ValueError(f'Valor inválido em {chave}')
    return valor


@mqtt.on_connect()
def handle_connect(client, userdata, flags, rc):
    if rc == 0:
        print('MQTT conectado')
        mqtt.subscribe(f'{PREFIXO}/+/vibracao')
        mqtt.subscribe(f'{PREFIXO}/+/rotacao')
        mqtt.subscribe(f'{PREFIXO}/+/rpm')
    else:
        print('Falha na conexão MQTT, rc =', rc)


@mqtt.on_message()
def handle_message(client, userdata, message):
    partes = message.topic.split('/')
    if len(partes) != 3 or partes[0] != PREFIXO or partes[1] not in MOTORES:
        return
    motor, tipo = partes[1], partes[2]
    if tipo not in ('vibracao',) + TIPOS_ROTACAO:
        return

    try:
        d = json.loads(message.payload.decode('utf-8'))
        if not isinstance(d, dict):
            return
        agora = time.time()
        ts = numero(d, 'ts', 0) or 0
        ts_valido = ts if ts > 1.6e9 else agora

        if tipo in TIPOS_ROTACAO:
            rpm = numero(d, 'rpm')
            ok = int(d.get('ok', 1)) == 1
            if rpm is None or not 0 <= rpm < 10000:
                return
            with rpm_lock:
                rpm_atual[motor] = {
                    'rpm': rpm if ok else None,
                    'recebido_em': agora,
                    'ts': ts_valido,
                    'ok': ok,
                }
            return

        # Mensagem de vibração: os indicadores de validade dos sensores são
        # independentes. Dados inválidos não são apresentados como medições.
        mpu_ok = int(d.get('ok', 1)) == 1
        pz_ok = int(d.get('pz_ok', 0)) == 1

        rms = numero(d, 'rms') if mpu_ok else None
        pico = numero(d, 'pico') if mpu_ok else None
        rx = numero(d, 'rx') if mpu_ok else None
        ry = numero(d, 'ry') if mpu_ok else None
        rz = numero(d, 'rz') if mpu_ok else None
        mpu_erros = int(d.get('erros', 0) or 0)

        pz_rms = numero(d, 'pz_rms') if pz_ok else None
        pz_pico = numero(d, 'pz_pico') if pz_ok else None
        pz_crista = numero(d, 'pz_crista') if pz_ok else None
        pz_dc = numero(d, 'pz_dc')
        pz_fs = int(d.get('pz_fs', 0) or 0)
        pz_clip = int(d.get('pz_clip', 0) or 0)

        # O firmware publica rms/pico mesmo quando ok=0. No banco legado,
        # esses campos eram NOT NULL; por isso usamos zero como sentinela e
        # mpu_ok=false para a interface exibir "--", não uma medição de zero.
        rpm = None
        with rpm_lock:
            ultimo = rpm_atual[motor]
        if ultimo and agora - ultimo['recebido_em'] <= RPM_MAX_IDADE_S and ultimo['ok']:
            rpm = ultimo['rpm']

        leitura = Leitura(
            motor=motor,
            t=ts_valido,
            ts_dispositivo=ts,
            recebido_em=agora,
            rms=rms if rms is not None else 0.0,
            pico=pico if pico is not None else 0.0,
            rpm=rpm,
            rx=rx, ry=ry, rz=rz,
            mpu_ok=mpu_ok,
            mpu_erros=mpu_erros,
            pz_rms=pz_rms,
            pz_pico=pz_pico,
            pz_crista=pz_crista,
            pz_dc=pz_dc,
            pz_fs=pz_fs,
            pz_clip=pz_clip,
            pz_ok=pz_ok,
        )

        with app.app_context():
            try:
                db.session.add(leitura)
                db.session.commit()
            except Exception:
                db.session.rollback()
                app.logger.exception('Falha ao gravar leitura')

    except (json.JSONDecodeError, UnicodeDecodeError, KeyError, TypeError, ValueError) as exc:
        app.logger.warning('Mensagem MQTT inválida em %s: %s', message.topic, exc)


def media(valores):
    valores = [v for v in valores if v is not None]
    return sum(valores) / len(valores) if valores else None


def reduzir(pontos, minutos, limite=MAX_PONTOS_API):
    """Agrupa pontos em intervalos; médias para RMS/RPM e máximos para picos."""
    if len(pontos) <= limite:
        return pontos
    largura = (minutos * 60) / limite
    baldes = {}
    for p in pontos:
        baldes.setdefault(int(p['t'] // largura), []).append(p)

    saida = []
    for g in (baldes[k] for k in sorted(baldes)):
        saida.append({
            'motor': g[0]['motor'],
            't': media([p['t'] for p in g]),
            'recebido_em': max(p['recebido_em'] for p in g),
            'rms': media([p['rms'] if p.get('mpu_ok') else None for p in g]),
            'pico': max([p['pico'] for p in g if p.get('mpu_ok') and p['pico'] is not None], default=None),
            'rpm': media([p['rpm'] for p in g]),
            'rx': media([p.get('rx') for p in g]),
            'ry': media([p.get('ry') for p in g]),
            'rz': media([p.get('rz') for p in g]),
            'mpu_ok': any(p.get('mpu_ok') for p in g),
            'mpu_erros': max([p.get('mpu_erros') or 0 for p in g], default=0),
            'pz_rms': media([p.get('pz_rms') for p in g if p.get('pz_ok')]),
            'pz_pico': max([p['pz_pico'] for p in g if p.get('pz_ok') and p.get('pz_pico') is not None], default=None),
            'pz_crista': media([p.get('pz_crista') for p in g if p.get('pz_ok')]),
            'pz_dc': media([p.get('pz_dc') for p in g]),
            'pz_fs': media([p.get('pz_fs') for p in g]),
            'pz_clip': max([p.get('pz_clip') or 0 for p in g], default=0),
            'pz_ok': any(p.get('pz_ok') for p in g),
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
