# FASE 2 — Simulador de sensores agrícolas con MQTT

Sistema de monitoreo de sensores IoT y analítica agroclimática para los cultivos de **caña de azúcar** (Valle del Cauca) y **arroz** (Tolima, Casanare) en Colombia.

---

## Archivos entregados

| Archivo | Propósito |
|---|---|
| `simulador_sensores.py` | **Simulador principal**. 32 sensores virtuales (8 variables × 4 parcelas) publicando vía MQTT con cadencias agronómicas. |
| `suscriptor_prueba.py` | Suscriptor MQTT en Python para evidenciar la recepción de mensajes (alternativa a `mosquitto_sub`). |
| `Fase2_Simulador_MQTT.ipynb` | Notebook Jupyter con el desarrollo paso a paso siguiendo la guía del docente. |
| `dataset_agroclimatico_colombia.csv` | Dataset de la Fase 1 (52.757 registros, 8 ubicaciones reales de Colombia). |
| `evidencia_publicaciones.jsonl` | Evidencia auditable de los mensajes publicados durante una corrida. |
| `evidencia_simulador_publisher.png` | Captura de la consola del simulador. |
| `evidencia_mosquitto_sub.png` | Captura de la consola de `mosquitto_sub` recibiendo mensajes. |
| `diagrama_arquitectura_mqtt.png` | Diagrama de la arquitectura MQTT desplegada. |
| `INSTALACION_MOSQUITTO.md` | Guía de instalación de Eclipse Mosquitto en macOS. |

---

## Inicio rápido (3 pasos)

### Paso 1 — Instalar dependencias

```bash
# Eclipse Mosquitto (broker MQTT) — ver INSTALACION_MOSQUITTO.md para detalles
brew install mosquitto

# Librerías Python
pip install paho-mqtt pandas
```

### Paso 2 — Iniciar el broker

```bash
brew services start mosquitto
# Verificar:
lsof -iTCP:1883 -sTCP:LISTEN
```

### Paso 3 — Ejecutar el simulador en 3 terminales

```bash
# Terminal 1 — Mosquitto verbose (opcional, para ver actividad del broker)
mosquitto -v

# Terminal 2 — Suscriptor (evidencia de recepción)
mosquitto_sub -h localhost -t "agricultura/#" -v

# Terminal 3 — Simulador (publisher)
python simulador_sensores.py --duracion 60 --max-mensajes 50
```

---

## Topología de las 4 parcelas

| ID | Cultivo | Ubicación | Departamento | Sistema |
|---|---|---|---|---|
| `parcela_1` | Caña de azúcar | Palmira | Valle del Cauca | Cenicaña RMA |
| `parcela_2` | Caña de azúcar | Candelaria | Valle del Cauca | Cenicaña RMA |
| `parcela_3` | Arroz | El Espinal | Tolima | Riego (FEDEARROZ-AMTEC) |
| `parcela_4` | Arroz | Yopal | Casanare | Secano (Llanos) |

Cada parcela tiene 8 sensores virtuales que monitorean: temperatura del aire, temperatura del suelo, humedad relativa, radiación solar, velocidad del viento, precipitación, humedad del suelo y pH del suelo.

## Estructura de tópicos MQTT

Convención jerárquica:
```
agricultura/<cultivo>/<parcela>/<variable>
```

Ejemplos:
```
agricultura/caña/parcela_1/temperatura_aire
agricultura/caña/parcela_1/humedad_suelo
agricultura/arroz/parcela_3/precipitacion
agricultura/arroz/parcela_4/ph_suelo
```

Suscripciones útiles con comodines MQTT:
```bash
mosquitto_sub -t "agricultura/#"                       # Todo
mosquitto_sub -t "agricultura/caña/#"                  # Solo caña
mosquitto_sub -t "agricultura/+/parcela_1/#"           # Todo de parcela_1
mosquitto_sub -t "agricultura/+/+/temperatura_aire"    # T° aire de todas las parcelas
```

## Estructura del payload JSON

```json
{
  "timestamp_real":     "2026-04-27T01:55:24.142+00:00",
  "timestamp_simulado": "2024-06-15T10:00:00",
  "parcela":            "parcela_1",
  "cultivo":            "caña",
  "ubicacion":          "Palmira_VAC",
  "variable":           "temperatura_aire",
  "valor":              24.32,
  "unidad":             "°C",
  "sensor_id":          "parcela_1_temperatura_aire"
}
```

## Frecuencias de publicación

| Variable | Frecuencia real (campo) | Frecuencia simulada (factor 60×) |
|---|---|---|
| Temperatura del aire | 5 min | 5 s |
| Humedad relativa | 5 min | 5 s |
| Radiación solar | 5 min | 5 s |
| Velocidad del viento | 10 min | 10 s |
| Temperatura del suelo | 10 min | 10 s |
| Humedad del suelo | 15 min | 15 s |
| Precipitación | 1 min | 1 s |
| pH del suelo | 1 hora | 60 s |

El factor de aceleración se controla con la variable de entorno `FACTOR_ACELERACION`:

```bash
FACTOR_ACELERACION=120 python simulador_sensores.py   # 1 min real = 2 h simuladas
FACTOR_ACELERACION=1   python simulador_sensores.py   # tiempo real
```

## Argumentos del simulador

```bash
python simulador_sensores.py [opciones]

  --dataset PATH         Ruta al CSV de la Fase 1 (default: dataset_agroclimatico_colombia.csv)
  --broker HOST          Host del broker MQTT (default: localhost)
  --puerto N             Puerto MQTT (default: 1883)
  --duracion SEG         Detener todo el simulador tras N segundos
  --max-mensajes N       Detener cada hilo tras N mensajes (útil para evidencia)
  --evidencia ARCHIVO    Archivo JSONL con todos los mensajes (default: evidencia_publicaciones.jsonl)
```

## Variables de entorno

```bash
export MQTT_BROKER_HOST="localhost"     # Host del broker
export MQTT_BROKER_PORT="1883"          # Puerto
export MQTT_USER="usuario"              # Usuario (si el broker requiere auth)
export MQTT_PASS="password"             # Contraseña
export FACTOR_ACELERACION="60"          # Aceleración temporal
```

## Adaptar a otros datasets

Para usar un dataset distinto (por ejemplo el `Soil Climate Crop Dataset` de Kaggle), basta con editar el diccionario `MAPEO_DATASET` en `simulador_sensores.py`:

```python
MAPEO_DATASET = {
    "temperatura_aire": "Temperature",   # nombre de la columna en TU CSV
    "humedad_relativa": "Humidity",
    "precipitacion":    "Rainfall",
    "ph_suelo":         "Soil_pH",
    # ... el simulador omitirá variables no mapeadas
}
```

Y la lista `PARCELAS` para usar las ubicaciones de tu dataset:

```python
PARCELAS = [
    {"id": "parcela_1", "cultivo": "caña",  "ubicacion": "MI_UBICACION", ...},
    ...
]
```

---

## Cumplimiento de los entregables del PDF

| Requisito de la Fase 2 | Cumplido | Evidencia |
|---|---|---|
| Script Python del simulador | ✅ | `simulador_sensores.py` (production-ready) |
| Evidencia de publicación MQTT | ✅ | `evidencia_publicaciones.jsonl`, `evidencia_simulador_publisher.png` |
| Captura del broker recibiendo mensajes | ✅ | `evidencia_mosquitto_sub.png` |
| Mínimo 4 parcelas simuladas | ✅ | 4 parcelas (2 caña + 2 arroz) — ver `PARCELAS` en el simulador |
| Generación de flujo de datos | ✅ | 32 sensores publicando concurrentemente con cadencias agronómicas diferenciadas |

---

## Próxima fase

**Fase 3 — Ingestión y almacenamiento de datos IoT**: el flujo `Sensores → MQTT → Node-RED Gateway → InfluxDB` se implementará. El simulador actual queda listo para conectarse sin cambios.
