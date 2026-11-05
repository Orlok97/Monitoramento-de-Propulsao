from extensions import db


class Leitura(db.Model):
    __tablename__ = 'leituras'
    id = db.Column(db.Integer, primary_key=True)
    motor = db.Column(db.String(2), nullable=False)
    t = db.Column(db.Float, nullable=False)
    ts_dispositivo = db.Column(db.Float)
    recebido_em = db.Column(db.Float, nullable=False)

    # MPU-6050: RMS e pico da aceleração resultante, além dos eixos.
    # Zero é sentinela apenas para compatibilidade com bancos antigos;
    # mpu_ok informa se a medição é válida.
    rms = db.Column(db.Float, nullable=False, default=0.0)
    pico = db.Column(db.Float)
    rx = db.Column(db.Float)
    ry = db.Column(db.Float)
    rz = db.Column(db.Float)
    mpu_ok = db.Column(db.Boolean, nullable=False, default=True)
    mpu_erros = db.Column(db.Integer)

    # Rotação obtida do tacômetro.
    rpm = db.Column(db.Float)

    # Piezo: grandezas relativas em contagens ADC, não em m/s².
    pz_rms = db.Column(db.Float)
    pz_pico = db.Column(db.Float)
    pz_crista = db.Column(db.Float)
    pz_dc = db.Column(db.Float)
    pz_fs = db.Column(db.Integer)
    pz_clip = db.Column(db.Integer)
    pz_ok = db.Column(db.Boolean, nullable=False, default=False)

    __table_args__ = (db.Index('idx_leituras_motor_t', 'motor', 't'),)

    def to_dict(self):
        return {
            'motor': self.motor,
            't': self.t,
            'recebido_em': self.recebido_em,
            'rms': self.rms if self.mpu_ok else None,
            'pico': self.pico if self.mpu_ok else None,
            'rx': self.rx if self.mpu_ok else None,
            'ry': self.ry if self.mpu_ok else None,
            'rz': self.rz if self.mpu_ok else None,
            'mpu_ok': bool(self.mpu_ok),
            'mpu_erros': self.mpu_erros,
            'rpm': self.rpm,
            'pz_rms': self.pz_rms if self.pz_ok else None,
            'pz_pico': self.pz_pico if self.pz_ok else None,
            'pz_crista': self.pz_crista if self.pz_ok else None,
            'pz_dc': self.pz_dc,
            'pz_fs': self.pz_fs,
            'pz_clip': self.pz_clip,
            'pz_ok': bool(self.pz_ok),
        }

    def __repr__(self):
        return f'<Leitura {self.motor} t={self.t} rpm={self.rpm}>'
