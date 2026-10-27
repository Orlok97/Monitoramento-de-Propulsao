from extensions import db


class Leitura(db.Model):
    __tablename__ = 'leituras'
    id = db.Column(db.Integer, primary_key=True)
    motor = db.Column(db.String(2), nullable=False)
    t = db.Column(db.Float, nullable=False)                  
    ts_dispositivo = db.Column(db.Float)                     
    recebido_em = db.Column(db.Float, nullable=False)
    rms = db.Column(db.Float, nullable=False)
    pico = db.Column(db.Float)
    rpm = db.Column(db.Float, nullable=False)

    __table_args__ = (
        db.Index('idx_leituras_motor_t', 'motor', 't'),
    )

    def to_dict(self):
        return {
            'motor': self.motor,
            't': self.t,
            'recebido_em': self.recebido_em,
            'rms': self.rms,
            'pico': self.pico,
            'rpm': self.rpm,
        }

    def __repr__(self):
        return f'<Leitura {self.motor} t={self.t} rms={self.rms} rpm={self.rpm}>'