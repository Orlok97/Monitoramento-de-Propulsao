# Monitoramento de Propulsão — versão de teste com 3 ESP32

Esta versão mantém os painéis do projeto e adapta a recepção para a arquitetura de teste com três ESP32:

1. **ESP32 nº 1 — rotação:** deve publicar a rotação de ambos os motores em dois tópicos independentes:
   - `<PREFIXO>/bb/rotacao`
   - `<PREFIXO>/be/rotacao`
2. **ESP32 nº 2 — vibração BB:** publica em `<PREFIXO>/bb/vibracao`.
3. **ESP32 nº 3 — vibração BE:** publica em `<PREFIXO>/be/vibracao`.

O ESP32 nº 1 precisa publicar JSON com pelo menos `rpm` e, opcionalmente, `ok` e `ts`.
Exemplo:
```json
{"rpm":1452.3,"pulsos":25,"ok":1,"ts":1761312000}
```

Os ESP32 de vibração publicam o formato utilizado pelo arquivo `no_vibracao_mpu_piezo.ino`:
```json
{
  "rms":0.42, "pico":1.10, "rx":0.30, "ry":0.25, "rz":0.18,
  "ok":1, "erros":0,
  "pz_rms":12.40, "pz_pico":85.0, "pz_crista":6.85, "pz_dc":1980,
  "pz_fs":4700, "pz_clip":0, "pz_ok":1, "ts":1761312000
}
```

## O que a aplicação faz

- Assina os tópicos `+/rotacao`, `+/rpm` (compatibilidade) e `+/vibracao` sob o prefixo configurado.
- Mantém em memória o RPM mais recente de cada motor.
- Ao receber uma janela de vibração, associa o RPM mais recente daquele motor, desde que tenha sido recebido nos últimos 3 segundos.
- Armazena no SQLite os dados do MPU-6050, do piezoelétrico, o RPM associado, indicadores de validade e informações de diagnóstico.
- Não apresenta como medição válida os valores de um sensor quando `ok=0` ou `pz_ok=0`.
- Mantém os cartões dos motores, gráficos temporais, gráfico de dispersão e tabela; acrescenta gráfico temporal do piezo e indicadores de validade dos dois sensores.

## Atenção: o sketch `no_rotacao.ino` original é de um motor

O sketch fornecido no conjunto original contém `#define MOTOR "bb"` e apenas uma entrada (`PINO_TACO`). Portanto, ele mede **um tacômetro por placa**, não os dois motores simultaneamente. Para a arquitetura de três ESP32, o firmware do primeiro ESP32 deve ser adaptado para:
- ler duas entradas de tacômetro independentes;
- calcular o RPM de BB e BE separadamente;
- publicar cada resultado no respectivo tópico (`bb/rotacao` e `be/rotacao`).

A aplicação já está preparada para receber os dois tópicos. Não conecte os sinais dos tacômetros diretamente aos GPIOs sem confirmar o tipo, amplitude e condicionamento elétrico. As entradas do ESP32 devem permanecer dentro dos limites elétricos da placa.

## Configuração

1. Instale as dependências:
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux/macOS:
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. Copie `.env.example` para `.env` e configure:
   - `MQTT_BROKER_URL`
   - `MQTT_BROKER_PORT`
   - `MQTT_USERNAME` / `MQTT_PASSWORD`, se aplicável
   - `MQTT_TOPIC_PREFIX`: exatamente o mesmo prefixo gravado nos três ESP32.
3. Execute:
   ```bash
   python app.py
   ```
4. Acesse `http://localhost:5000`.

## Interpretação das métricas

- **MPU RMS e pico:** aceleração resultante filtrada, em m/s², conforme o processamento do firmware.
- **rx, ry, rz:** RMS de cada eixo do MPU-6050, em m/s².
- **Piezo RMS, pico e fator de crista:** grandezas relativas em contagens do ADC; não são m/s² e não devem ser comparadas numericamente com o MPU.
- **pz_fs e pz_clip:** diagnóstico da taxa real de amostragem e de saturação do ADC.
- **RPM:** valor obtido do sinal do tacômetro e associado à leitura de vibração mais recente do mesmo motor.

O fator de crista e os níveis de vibração são indicadores para comparação entre condições semelhantes. Não constituem, isoladamente, diagnóstico de desalinhamento ou falha mecânica. Para comparação técnica, mantenha posição, orientação, fixação, configuração e regime de operação dos sensores consistentes.

## Banco SQLite existente

Na inicialização, a aplicação acrescenta ao banco `leituras` as colunas novas que não existirem. Faça uma cópia de segurança do arquivo SQLite antes de substituir a versão anterior da aplicação.
