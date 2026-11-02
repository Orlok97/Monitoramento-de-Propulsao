# Sistema IoT para Monitoramento da Condição do Sistema de Propulsão de Embarcações

Projeto Integrador VI · UNIVESP · Engenharia da Computação

## Menu

- [Descrição do projeto](#descrição-do-projeto)
- [Instalação e configuração](#instalação-e-configuração)
- [Firmware ESP32 (3 módulos)](#firmware-esp32-3-módulos)
- [Autores](#autores)

---

## Descrição do projeto

Sistema de monitoramento dos motores de bombordo (**BB**) e boreste (**BE**) de uma embarcação de trabalho. Três módulos ESP32 coletam os dados: **dois na sala de máquinas** medem a **vibração** (MPU-6050 / piezoelétrico), um por motor, e **um na cabine** lê os sinais dos dois **tacômetros** (rotação). Os módulos publicam via **MQTT**. Esta aplicação Flask recebe as mensagens, associa cada leitura de vibração ao RPM mais recente do mesmo motor, grava o histórico em banco de dados e exibe a relação vibração × RPM em um dashboard web, apoiando a manutenção preditiva.

```
ESP32 vibração BB (sala de máquinas) ──┐
ESP32 vibração BE (sala de máquinas) ──┼── Wi-Fi / MQTT ──> Broker ──> Flask + Banco de Dados ──> Dashboard web
ESP32 tacômetros BB + BE (cabine) ─────┘
```

| Tópico | Publicado por | Payload |
|---|---|---|
| `<PREFIXO>/bb/vibracao` e `<PREFIXO>/be/vibracao` | ESP32 de vibração do motor | `{"rms": 0.4210, "pico": 1.1032, "ts": 1761312000}` |
| `<PREFIXO>/bb/rpm` e `<PREFIXO>/be/rpm` | ESP32 dos tacômetros | `{"rpm": 1450, "ts": 1761312000}` |

| Campo | Descrição |
|---|---|
| `rms` | Vibração (valor eficaz da aceleração, m/s²) |
| `pico` | Maior aceleração na janela (m/s²) |
| `rpm` | Rotação do motor |
| `ts` | Timestamp do ESP32 (`0` se sem NTP; vale a hora do servidor) |

**Como vibração e RPM se encontram:** como vêm de placas diferentes, o Flask guarda o último RPM de cada motor e o associa à vibração que chegar em até 3 s (`RPM_MAX_IDADE_S` no `app.py`). Passado esse tempo sem RPM novo, a leitura é gravada com `rpm` nulo e aparece como `--` no dashboard.

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

> `broker.emqx.io` é público: qualquer pessoa pode ler e publicar no seu tópico. Use no `.env` um prefixo **diferente** do exemplo do repositório, único e difícil de adivinhar. Para dados reais, prefira um broker privado com autenticação e TLS.
> Não faça commit do `.env`. Mantenha também `instance/`, `venv/` e `node_modules/` no `.gitignore`.

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

# RPM (cabine) e vibração (sala de máquinas) de cada motor. Publique o RPM primeiro e repita a cada ~1 s
mosquitto_pub -h broker.emqx.io -t "SEU-PREFIXO/bb/rpm"      -m '{"rpm":1450,"ts":0}'
mosquitto_pub -h broker.emqx.io -t "SEU-PREFIXO/bb/vibracao" -m '{"rms":0.42,"pico":1.10,"ts":0}'

mosquitto_pub -h broker.emqx.io -t "SEU-PREFIXO/be/rpm"      -m '{"rpm":1480,"ts":0}'
mosquitto_pub -h broker.emqx.io -t "SEU-PREFIXO/be/vibracao" -m '{"rms":0.38,"pico":0.95,"ts":0}'
```

Só a mensagem de **vibração** gera uma linha no banco. Se o RPM do mesmo motor tiver chegado nos últimos 3 s, ele é gravado junto. Caso contrário, a linha fica com `rpm` nulo.


## Firmware ESP32 (3 módulos)

Exemplos de código para a Arduino IDE. A vibração fica na sala de máquinas e os tacômetros na cabine, então são **3 módulos**:

| Módulo | Local | Lê | Publica em |
|---|---|---|---|
| ESP32 de vibração BB | sala de máquinas | MPU-6050 do bombordo | `<PREFIXO>/bb/vibracao` |
| ESP32 de vibração BE | sala de máquinas | MPU-6050 do boreste | `<PREFIXO>/be/vibracao` |
| ESP32 dos tacômetros | cabine | tacômetros dos dois motores | `<PREFIXO>/bb/rpm` e `<PREFIXO>/be/rpm` |

**Bibliotecas:** pacote de placas **esp32** (Espressif), **PubSubClient** e **Adafruit MPU6050**.

**Ligação:**
- **Vibração:** MPU-6050 em `3V3`, `GND`, `SDA` (GPIO 21) e `SCL` (GPIO 22).
- **Tacômetros:** BB no GPIO 34 e BE no GPIO 35, **depois de condicionados** (máx. 3,3 V). Nunca ligue o sinal do motor direto no pino.

Antes de gravar, ajuste `WIFI_SSID`, `WIFI_PASS`, `PREFIXO` (igual ao `MQTT_TOPIC_PREFIX` do Flask) e `PULSOS_POR_VOLTA`. Os três módulos precisam de internet para o NTP preencher o campo `ts`.

### ESP32 de vibração do bombordo (BB)

```cpp
// Nó de VIBRAÇÃO (sala de máquinas), um por motor.
// Publica em <PREFIXO>/<MOTOR>/vibracao:
//   {"rms":0.4210,"pico":1.1032,"ts":1761312000}

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

  topico   = String(PREFIXO) + "/" + MOTOR + "/vibracao";
  clientId = String(PREFIXO) + "-vib-" + MOTOR + "-" + String((uint32_t)ESP.getEfuseMac(), HEX);

  Wire.begin();                              // SDA=21, SCL=22
  Wire.setClock(400000);
  if (!mpu.begin()) {
    Serial.println("MPU-6050 nao encontrado. Confira a fiacao.");
    while (true) delay(1000);
  }
  mpu.setAccelerometerRange(MPU6050_RANGE_4_G);
  mpu.setFilterBandwidth(MPU6050_BAND_260_HZ);

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

  // 1) Janela de aquisição
  unsigned long proxima = micros();
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

  // 2) RMS e pico sem a componente DC (gravidade)
  float media = soma / N_AMOSTRAS;
  float somaQuad = 0, pico = 0;
  for (int i = 0; i < N_AMOSTRAS; i++) {
    float d = mag[i] - media;
    somaQuad += d * d;
    if (fabsf(d) > pico) pico = fabsf(d);
  }
  float rms = sqrtf(somaQuad / N_AMOSTRAS);

  time_t agora = time(nullptr);
  unsigned long ts = (agora > 1600000000) ? (unsigned long)agora : 0;   // 0 = sem NTP

  // 3) Publica
  char payload[96];
  snprintf(payload, sizeof(payload),
           "{\"rms\":%.4f,\"pico\":%.4f,\"ts\":%lu}", rms, pico, ts);

  if (mqtt.connected()) mqtt.publish(topico.c_str(), payload);
  Serial.println(payload);
}
```

### ESP32 de vibração do boreste (BE)

O código é idêntico ao do BB. Troque apenas esta linha, e o tópico passa a ser `<PREFIXO>/be/vibracao`:

```cpp
#define MOTOR "be"                          // "bb" (bombordo) ou "be" (boreste)
```

### ESP32 dos tacômetros (cabine)

Um único ESP32 lê os dois tacômetros, que ficam próximos, e publica um RPM por motor.

```cpp
// Nó dos TACÔMETROS (cabine): lê BB e BE no mesmo ESP32.
// Publica em <PREFIXO>/bb/rpm e <PREFIXO>/be/rpm:
//   {"rpm":1450,"ts":1761312000}

#include <WiFi.h>
#include <PubSubClient.h>
#include <time.h>

// ===================== CONFIGURAÇÃO =====================
const char* WIFI_SSID = "SEU_WIFI";
const char* WIFI_PASS = "SUA_SENHA";

const char* MQTT_HOST = "broker.emqx.io";
const int   MQTT_PORT = 1883;
const char* PREFIXO   = "SEU-PREFIXO";      // o MESMO do MQTT_TOPIC_PREFIX do Flask

const int   N_MOTORES = 2;                  // índice 0 = BB, índice 1 = BE
const char* IDS[N_MOTORES]               = { "bb", "be" };
const int   PINO_TACO[N_MOTORES]         = { 34, 35 };   // entradas JÁ condicionadas (máx. 3,3 V)
const float PULSOS_POR_VOLTA[N_MOTORES]  = { 1.0, 1.0 }; // AJUSTAR conforme o sinal do tacômetro

const unsigned long JANELA_MS = 1000;       // intervalo entre publicações
// ========================================================

WiFiClient wifi;
PubSubClient mqtt(wifi);

String topicos[N_MOTORES];
String clientId;
unsigned long ultimaTentativaMs = 0;
unsigned long inicioJanela = 0;

volatile unsigned long pulsos[N_MOTORES] = { 0, 0 };
volatile unsigned long ultimoPulsoUs[N_MOTORES] = { 0, 0 };

// Uma única ISR para os dois tacômetros: o índice do motor chega pelo argumento
void IRAM_ATTR contarPulso(void* arg) {
  int m = (int)(intptr_t)arg;
  unsigned long agora = micros();
  if (agora - ultimoPulsoUs[m] > 200) {     // debounce simples (200 µs)
    pulsos[m]++;
    ultimoPulsoUs[m] = agora;
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

  clientId = String(PREFIXO) + "-taco-" + String((uint32_t)ESP.getEfuseMac(), HEX);
  for (int m = 0; m < N_MOTORES; m++) {
    topicos[m] = String(PREFIXO) + "/" + IDS[m] + "/rpm";
    pinMode(PINO_TACO[m], INPUT);
    attachInterruptArg(digitalPinToInterrupt(PINO_TACO[m]), contarPulso, (void*)(intptr_t)m, RISING);
  }

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("WiFi");
  while (WiFi.status() != WL_CONNECTED) { delay(300); Serial.print("."); }
  Serial.println(" ok: " + WiFi.localIP().toString());

  configTime(0, 0, "pool.ntp.org", "time.google.com");   // horário para o campo "ts"
  for (int i = 0; i < 20 && time(nullptr) < 1600000000; i++) delay(500);

  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setKeepAlive(30);
  inicioJanela = millis();
}

void loop() {
  garantirConexoes();
  mqtt.loop();

  unsigned long agora = millis();
  if (agora - inicioJanela < JANELA_MS) return;

  // Lê e zera os contadores no mesmo instante, para os dois motores
  unsigned long p[N_MOTORES];
  noInterrupts();
  for (int m = 0; m < N_MOTORES; m++) { p[m] = pulsos[m]; pulsos[m] = 0; }
  interrupts();

  float segundos = (agora - inicioJanela) / 1000.0f;
  inicioJanela = agora;

  time_t t = time(nullptr);
  unsigned long ts = (t > 1600000000) ? (unsigned long)t : 0;   // 0 = sem NTP

  for (int m = 0; m < N_MOTORES; m++) {
    float rpm = (p[m] / PULSOS_POR_VOLTA[m]) / segundos * 60.0f;

    char payload[64];
    snprintf(payload, sizeof(payload), "{\"rpm\":%.0f,\"ts\":%lu}", rpm, ts);

    if (mqtt.connected()) mqtt.publish(topicos[m].c_str(), payload);
    Serial.printf("[%s] %s\n", IDS[m], payload);
  }
}
```

Pontos de atenção:

- **Sincronização:** vibração e RPM saem de placas diferentes, então o pareamento é feito pelo Flask (janela de 3 s). Para análises mais precisas no futuro, use o `ts` (NTP) dos dois módulos.
- **Resolução do RPM:** com 1 pulso por volta e janela de 1 s, a resolução é de 60 RPM. Se o tacômetro gerar mais pulsos por volta, ajuste `PULSOS_POR_VOLTA`.
- **Wi-Fi na sala de máquinas:** o ambiente é metálico e pode atenuar o sinal. Teste a cobertura antes de fixar os módulos.

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