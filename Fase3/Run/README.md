# FASE 3 — Ingesta y almacenamiento de datos IoT en InfluxDB

Pipeline completo de ingesta IoT para el sistema de monitoreo agroclimático: los mensajes MQTT publicados por el simulador (Fase 2) son capturados por un Gateway Node-RED y persistidos en InfluxDB v2 como serie de tiempo.

---

## Archivos entregados

| Archivo | Propósito |
|---|---|
| `Fase3_Ingesta_InfluxDB.ipynb` | Notebook Jupyter con queries de validación contra InfluxDB. |
| `flow_node_red.json` | Flow Node-RED listo para importar (MQTT→Function→InfluxDB). |
| `INSTALACION_INFLUXDB_NODERED.md` | Guía paso a paso de instalación en macOS (Homebrew). |
| `evidencia_nodered_flow.png` | Captura del flow Node-RED (Entregable 1). |
| `evidencia_mosquitto_config.png` | Configuración del broker Mosquitto (Entregable 2). |
| `evidencia_influxdb_bucket.png` | Bucket creado en InfluxDB (Entregable 3). |
| `evidencia_influxdb_data_explorer.png` | Datos almacenados en Data Explorer (Entregable 4). |
| `diagrama_arquitectura_fase3.png` | Diagrama completo de la arquitectura. |
| `README.md` | Este archivo. |

---

## Inicio rápido (5 pasos)

### Paso 1 — Instalar el stack

```bash
# (Mosquitto ya debería estar de la Fase 2)
brew services start mosquitto

# InfluxDB v2 (NO el comando 'brew install influxdb' — ese instala v3)
brew install influxdb@2 influxdb-cli
brew services start influxdb@2

# Node-RED
npm install -g --unsafe-perm node-red

# Cliente Python para el notebook
pip install influxdb-client pandas
```

> Detalles completos en `INSTALACION_INFLUXDB_NODERED.md`.

### Paso 2 — Configurar InfluxDB (UI inicial)

1. Abrir `http://localhost:8086`.
2. Setup inicial: **Username**, **Password**, **Org=agricultura**, **Bucket=agro_iot_data**.
3. Copiar el Operator Token mostrado al final.
4. (Recomendado) Crear un token específico para Node-RED en **Load Data → API Tokens**, con permisos R/W solo sobre `agro_iot_data`.

### Paso 3 — Importar el flow en Node-RED

1. Iniciar Node-RED: `node-red`
2. Abrir `http://localhost:1880`.
3. Menú ☰ → **Import** → seleccionar `flow_node_red.json`.
4. Doble clic en el nodo **InfluxDB Out** → editar Server → pegar el token.
5. Clic en **Deploy** (botón rojo, esquina superior derecha).

### Paso 4 — Iniciar el simulador (Fase 2)

```bash
cd /ruta/a/fase2
python simulador_sensores.py --duracion 120
```

### Paso 5 — Verificar que los datos llegan

**Opción A — Notebook:**
```bash
export INFLUX_TOKEN="<tu-token>"
jupyter notebook Fase3_Ingesta_InfluxDB.ipynb
```

**Opción B — UI de InfluxDB:**
1. Abrir `http://localhost:8086` → **Data Explorer**.
2. Construir query sobre `agro_iot_data`, filtrar `_measurement == sensor_data`.
3. Submit → ver los datos llegando en vivo.

---

## Modelo de datos en InfluxDB

```
Bucket:        agro_iot_data
Organization:  agricultura
Measurement:   sensor_data

Tags (indexados — ideales para filtrar):
  parcela     ∈ {parcela_1, parcela_2, parcela_3, parcela_4}
  cultivo     ∈ {caña, arroz}
  ubicacion   ∈ {Palmira_VAC, Candelaria_VAC, Espinal_TOL, Yopal_CAS}
  variable    ∈ {temperatura_aire, humedad_relativa, precipitacion,
                 radiacion_solar, velocidad_viento, humedad_suelo,
                 ph_suelo, temperatura_suelo}
  unidad      ∈ {°C, %, mm, MJ/m2/dia, m/s, pH}
  sensor_id   ∈ {parcela_1_temperatura_aire, ...}

Fields (numéricos — el valor de la medición):
  <nombre_variable>: float    ← campo dinámico cuyo nombre coincide con el tag 'variable'

Timestamp: timestamp_real del payload MQTT (UTC, precisión ms)
```

### Por qué este modelo

InfluxDB optimiza las queries por **tags**, no por fields. Filtrar por `parcela='parcela_1'` o `cultivo='caña'` es prácticamente gratis. Usar un **field dinámico** llamado igual que `variable` permite agregar variables nuevas sin cambiar el flow Node-RED — basta con que el simulador empiece a publicar otra variable y se almacenará automáticamente.

---

## Consultas Flux útiles

### Últimos 10 minutos
```flux
from(bucket: "agro_iot_data")
  |> range(start: -10m)
  |> filter(fn: (r) => r._measurement == "sensor_data")
```

### Temperatura promedio por parcela
```flux
from(bucket: "agro_iot_data")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "sensor_data" and r._field == "temperatura_aire")
  |> group(columns: ["parcela"])
  |> mean()
```

### Precipitación acumulada diaria por parcela
```flux
from(bucket: "agro_iot_data")
  |> range(start: -7d)
  |> filter(fn: (r) => r._measurement == "sensor_data" and r._field == "precipitacion")
  |> aggregateWindow(every: 1d, fn: sum, createEmpty: false)
  |> group(columns: ["parcela"])
```

### Solo datos de cultivos cañeros del Valle del Cauca
```flux
from(bucket: "agro_iot_data")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "sensor_data" and r.cultivo == "caña")
```

---

## Sobre el formato de mensajes — diferencia con el PDF docente

**El PDF de la Fase 3** muestra un payload simplificado donde TODAS las variables vienen en UN solo mensaje JSON:
```json
{ "temperature_air": 24.5, "humidity": 75.2, "precipitation": 0.0, "soil_ph": 6.8, ... }
```

**Nuestro simulador (Fase 2)** sigue el patrón **un mensaje por sensor por variable**, que es agronómicamente más correcto:
```json
{ "variable": "temperatura_aire", "valor": 24.5, "parcela": "parcela_1",
  "cultivo": "caña", "ubicacion": "Palmira_VAC", "unidad": "°C", ... }
```

Esto se debe a que cada variable tiene su propia frecuencia natural de medición:

- Temperatura/Humedad: cada 5 min
- Precipitación: por evento (basculación del pluviómetro)
- pH del suelo: cada 1 hora

Forzar todas en un único mensaje obligaría a usar la frecuencia más alta para todo (desperdicio de ancho de banda y batería de los sensores). El flow Node-RED se adaptó a este formato real mediante un **field dinámico** cuyo nombre coincide con `payload.variable`.

---

## Cumplimiento de los entregables

| # | Entregable del PDF | Cumplido | Evidencia |
|---|---|---|---|
| 1 | Captura del flow Node-RED | ✅ | `evidencia_nodered_flow.png` |
| 2 | Configuración del broker MQTT | ✅ | `evidencia_mosquitto_config.png` |
| 3 | Base de datos creada en InfluxDB | ✅ | `evidencia_influxdb_bucket.png` |
| 4 | Evidencia de almacenamiento | ✅ | `evidencia_influxdb_data_explorer.png` |
| 5 | Consulta mostrando registros | ✅ | sección 5 del notebook (3 queries Flux con resultados reales) |

---

## Solución de problemas

Ver sección 6 de `INSTALACION_INFLUXDB_NODERED.md` para los problemas más comunes y sus soluciones.

---

## Próxima fase

**Fase 4 — Procesamiento de datos en tiempo real:** se añadirán tasks Flux en InfluxDB para limpieza automática y agregaciones, y nodos function adicionales en Node-RED para detección de outliers y enrutamiento a tópicos de alerta.
