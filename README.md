# Sistema IoT para Monitoramento da Condição do Sistema de Propulsão de Embarcações

Projeto Integrador VI · UNIVESP · Engenharia da Computação

## Menu

- [Descrição do projeto](#descrição-do-projeto)
- [Instalação e configuração](#instalação-e-configuração)
- [Firmware ESP32 (motores BB e BE)](#firmware-esp32-motores-bb-e-be)
- [Autores](#autores)

---

## Descrição do projeto

Sistema de monitoramento dos motores de bombordo (**BB**) e boreste (**BE**) de uma embarcação de trabalho. Dispositivos ESP32 medem a **vibração** (MPU-6050 / piezoelétrico) e a **rotação** (sinal do tacômetro) de cada motor e publicam os dados via **MQTT**. Esta aplicação Flask recebe as mensagens, grava o histórico em banco de dados e exibe a relação vibração × RPM em um dashboard web, apoiando a manutenção preditiva.

```
ESP32 (BB) ──┐
             ├── Wi-Fi / MQTT ──> Broker ──> Flask + SQLite ──> Dashboard web
ESP32 (BE) ──┘
```

Mensagens publicadas em `<PREFIXO>/bb/dados` e `<PREFIXO>/be/dados`:

```json
{"rms": 0.4210, "pico": 1.1032, "rpm": 1450, "ts": 1761312000}
```

| Campo | Descrição |
|---|---|
| `rms` | Vibração (valor eficaz da aceleração, m/s²) |
| `pico` | Maior aceleração na janela (m/s²) |
| `rpm` | Rotação do motor |
| `ts` | Timestamp do ESP32 (`0` se sem NTP; vale a hora do servidor) |

> Um nível de vibração isolado não prova desalinhamento do eixo. O sistema registra e correlaciona vibração e rotação para apoiar a investigação de alterações de comportamento.

---

## Instalação e configuração

### Pré-requisitos

Python 3.10+ e Node.js 18+ (o Node só é usado para gerar o CSS, não precisa estar no servidor).

### Estrutura

```
projeto/
├── app.py
├── config.py
├── extensions.py
├── requirements.txt
├── .env / .env.example
├── package.json
├── models/
│   ├── __init__.py
│   └── leitura.py
├── src/
│   └── input.css
├── views/
│   └── dashboard.html
└── static/
    ├── css/tailwind.css     ← gerado pelo Tailwind
    └── js/script.js
```

### 1. Ambiente virtual e dependências Python

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Variáveis de ambiente

Copie o modelo e preencha:

```bash
cp .env.example .env
```

| Variável | Descrição |
|---|---|
| `MQTT_BROKER_URL` | Endereço do broker, sem `mqtt://` e sem porta (ex.: `broker.emqx.io`) |
| `MQTT_BROKER_PORT` | Porta do broker (`1883` sem TLS, `8883` com TLS) |
| `MQTT_USERNAME` / `MQTT_PASSWORD` | Credenciais do broker (`''` em brokers públicos) |
| `MQTT_KEEPALIVE` | Intervalo de keepalive, em segundos (`60`) |
| `MQTT_REFRESH_TIME` | Intervalo do loop de rede do Flask-MQTT, em segundos (menor = menos latência) |
| `MQTT_TOPIC_PREFIX` | Prefixo dos tópicos. Deve ser **igual** ao dos ESP32 |
| `DATABASE_URL` | Banco de dados (ex.: `sqlite:///monitoramento.db`) |

### 3. Tailwind CSS

O `package.json` e o `src/input.css` já estão no repositório, então basta instalar as dependências listadas:

```bash
npm install
```

Gere o CSS (rode de novo sempre que alterar classes no HTML ou no `script.js`):

```bash
mkdir -p static/css

npm run css:watch    # desenvolvimento (regenera ao salvar)
npm run css:build    # produção (minificado)
```

Os atalhos estão no `package.json`:

```json
"scripts": {
  "css:watch": "tailwindcss -i ./src/input.css -o ./static/css/tailwind.css --watch",
  "css:build": "tailwindcss -i ./src/input.css -o ./static/css/tailwind.css --minify"
}
```

> Só na primeira vez, para **criar** o projeto (quem clonar o repositório não precisa): `npm init -y`, `npm install tailwindcss @tailwindcss/cli` e criar o `src/input.css` com `@import "tailwindcss";`.

O Chart.js é carregado pelo CDN. Referências no `views/dashboard.html`:

```html
<link rel="stylesheet" href="/static/css/tailwind.css">   <!-- no <head> -->

<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<script src="/static/js/script.js"></script>              <!-- fim do <body> -->
```

### 4. Executar
```bash
flask run
```
ou
```bash
python app.py
```

Dashboard em <http://localhost:5000> e API em `/api/ultimos` e `/api/historico?minutos=10`.

### 5. Testar sem o ESP32

```bash
sudo apt install mosquitto-clients
mosquitto_pub -h broker.emqx.io -t "SEU-PREFIXO/bb/dados" -m '{"rms":0.42,"pico":1.10,"rpm":1450,"ts":0}'
mosquitto_pub -h broker.emqx.io -t "SEU-PREFIXO/be/dados" -m '{"rms":0.38,"pico":0.95,"rpm":1480,"ts":0}'
```

## Firmware ESP32 (motores BB e BE)

Exemplo de código para a Arduino IDE. Cada motor tem **um ESP32** que lê a vibração (MPU-6050) e a rotação (tacômetro) e publica tudo em uma única mensagem. O código é o mesmo nos dois motores, e só muda a constante `MOTOR`.

**Bibliotecas:** pacote de placas **esp32** (Espressif), **PubSubClient** e **Adafruit MPU6050**.

**Ligação:** MPU-6050 em `3V3`, `GND`, `SDA` (GPIO 21) e `SCL` (GPIO 22). O tacômetro entra no GPIO 34, **depois de condicionado**. Nunca ligue o sinal do motor direto no pino.

### ESP32 do bombordo (BB)

Publica em `<PREFIXO>/bb/dados`.

```cpp
// Nó de monitoramento de UM motor: vibração (MPU-6050) + rotação (tacômetro).
// O mesmo código serve para os dois motores: só muda a constante MOTOR.
// Publica em <PREFIXO>/<MOTOR>/dados:
//   {"rms":0.4210,"pico":1.1032,"rpm":1450,"ts":1761312000}

#include <WiFi.h>
#include <PubSubClient.h>
#include <Wire.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <math.h>
#include <time.h>

// ===================== CONFIGURAÇÃO =====================
#define MOTOR "bb"                          // "bb" (bombordo) ou "be" (boreste)

const char* WIFI_SSID = "SEU_WIFI";
const char* WIFI_PASS = "SUA_SENHA";

const char* MQTT_HOST = "broker.emqx.io";
const int   MQTT_PORT = 1883;
const char* PREFIXO   = "SEU-PREFIXO";      // o MESMO do MQTT_TOPIC_PREFIX do Flask

const int   PINO_TACO        = 34;          // entrada do tacômetro (JÁ condicionada, máx. 3,3 V)
const float PULSOS_POR_VOLTA = 1.0;         // AJUSTAR conforme o sinal do tacômetro

const int   N_AMOSTRAS   = 200;             // amostras por janela
const unsigned long INTERVALO_US = 5000;    // 5 ms entre amostras (~200 Hz) => janela de ~1 s
// ========================================================

WiFiClient wifi;
PubSubClient mqtt(wifi);
Adafruit_MPU6050 mpu;

String topico;
String clientId;
unsigned long ultimaTentativaMs = 0;

float mag[N_AMOSTRAS];
volatile unsigned long pulsos = 0;
volatile unsigned long ultimoPulsoUs = 0;

void IRAM_ATTR contarPulso() {
  unsigned long agora = micros();
  if (agora - ultimoPulsoUs > 200) {        // debounce simples (200 µs)
    pulsos++;
    ultimoPulsoUs = agora;
  }
}

void garantirConexoes() {
  if (WiFi.status() != WL_CONNECTED) {
    if (millis() - ultimaTentativaMs > 5000) {
      ultimaTentativaMs = millis();
      Serial.println("WiFi desconectado, reconectando...");
      WiFi.disconnect();
      WiFi.begin(WIFI_SSID, WIFI_PASS);
    }
    return;
  }
  if (!mqtt.connected() && millis() - ultimaTentativaMs > 5000) {
    ultimaTentativaMs = millis();
    Serial.print("MQTT... ");
    if (mqtt.connect(clientId.c_str())) Serial.println("ok");
    else Serial.printf("falhou, rc=%d\n", mqtt.state());
  }
}

void setup() {
  Serial.begin(115200);

  topico   = String(PREFIXO) + "/" + MOTOR + "/dados";
  clientId = String(PREFIXO) + "-" + MOTOR + "-" + String((uint32_t)ESP.getEfuseMac(), HEX);

  Wire.begin();                              // SDA=21, SCL=22
  Wire.setClock(400000);
  if (!mpu.begin()) {
    Serial.println("MPU-6050 nao encontrado. Confira a fiacao.");
    while (true) delay(1000);
  }
  mpu.setAccelerometerRange(MPU6050_RANGE_4_G);
  mpu.setFilterBandwidth(MPU6050_BAND_260_HZ);

  pinMode(PINO_TACO, INPUT);
  attachInterrupt(digitalPinToInterrupt(PINO_TACO), contarPulso, RISING);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("WiFi");
  while (WiFi.status() != WL_CONNECTED) { delay(300); Serial.print("."); }
  Serial.println(" ok: " + WiFi.localIP().toString());

  configTime(0, 0, "pool.ntp.org", "time.google.com");   // horário para o campo "ts"
  for (int i = 0; i < 20 && time(nullptr) < 1600000000; i++) delay(500);

  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setKeepAlive(30);
  Serial.println("Topico: " + topico);
}

void loop() {
  garantirConexoes();
  mqtt.loop();

  // 1) Janela de aquisição: vibração e pulsos do tacômetro ao mesmo tempo
  noInterrupts(); pulsos = 0; interrupts();
  unsigned long inicio = micros();
  unsigned long proxima = inicio;
  float soma = 0;

  for (int i = 0; i < N_AMOSTRAS; i++) {
    sensors_event_t a, g, t;
    mpu.getEvent(&a, &g, &t);
    mag[i] = sqrtf(a.acceleration.x * a.acceleration.x +
                   a.acceleration.y * a.acceleration.y +
                   a.acceleration.z * a.acceleration.z);
    soma += mag[i];

    proxima += INTERVALO_US;
    while ((long)(micros() - proxima) < 0) { /* espera */ }
  }

  noInterrupts(); unsigned long p = pulsos; interrupts();
  float dt = (micros() - inicio) / 1e6f;

  // 2) RMS e pico sem a componente DC (gravidade)
  float media = soma / N_AMOSTRAS;
  float somaQuad = 0, pico = 0;
  for (int i = 0; i < N_AMOSTRAS; i++) {
    float d = mag[i] - media;
    somaQuad += d * d;
    if (fabsf(d) > pico) pico = fabsf(d);
  }
  float rms = sqrtf(somaQuad / N_AMOSTRAS);
  float rpm = (p / PULSOS_POR_VOLTA) / dt * 60.0f;

  time_t agora = time(nullptr);
  unsigned long ts = (agora > 1600000000) ? (unsigned long)agora : 0;   // 0 = sem NTP

  // 3) Publica vibração + rotação na mesma mensagem
  char payload[128];
  snprintf(payload, sizeof(payload),
           "{\"rms\":%.4f,\"pico\":%.4f,\"rpm\":%.0f,\"ts\":%lu}", rms, pico, rpm, ts);

  if (mqtt.connected()) mqtt.publish(topico.c_str(), payload);
  Serial.println(payload);
}
```

### ESP32 do boreste (BE)

O código é idêntico ao do BB. Troque apenas esta linha, e o tópico passa a ser `<PREFIXO>/be/dados`:

```cpp
#define MOTOR "be"                          // "bb" (bombordo) ou "be" (boreste)
```

Antes de gravar, ajuste `WIFI_SSID`, `WIFI_PASS`, `PREFIXO` (igual ao `MQTT_TOPIC_PREFIX` do Flask) e `PULSOS_POR_VOLTA`.

---

## Autores

- Alysson Ribeiro Lopes
- Arthur Rogerio Ferreira
- Diego Rodrigues de Alcantara
- Gisele Vieira de Amorim
- Johny Cristian Braz Vieira
- Julio Cesar Pereira de Freitas Filho
- Lauro Xavier Belardo

**Tutor:** Heitor Perrud Tardin

Universidade Virtual do Estado de São Paulo (UNIVESP) · Polo Cubatão, Guarujá, Praia Grande, Santos e São Vicente · 2026