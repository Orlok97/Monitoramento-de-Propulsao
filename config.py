import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    MQTT_BROKER_URL = os.getenv('MQTT_BROKER_URL')
    MQTT_BROKER_PORT = int(os.getenv('MQTT_BROKER_PORT', 1883))
    MQTT_USERNAME = os.getenv('MQTT_USERNAME', '')
    MQTT_PASSWORD = os.getenv('MQTT_PASSWORD', '')
    MQTT_KEEPALIVE = int(os.getenv('MQTT_KEEPALIVE', 60))
    MQTT_REFRESH_TIME = float(os.getenv('MQTT_REFRESH_TIME', 1.0))
    MQTT_TLS_ENABLED = False
    MQTT_TOPIC_PREFIX = os.getenv('MQTT_TOPIC_PREFIX', 'pi6-univesp-x7k2q')