# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SISCOM (Sistema Integral de Seguimiento de Cultivos Operando a Múltiples Escalas) is an end-to-end IoT and ML agroclimatic monitoring system for sugarcane and rice crops in Colombia. It is structured as 8 sequential phases (Fase0–Fase7), each in its own directory with a Jupyter notebook as the primary documentation artifact.

## Architecture

Data flows through the system in this order:

```
Fase2: simulador_sensores.py (32 virtual MQTT sensors)
  → Mosquitto broker (:1883)
  → Fase3: Node-RED (flow_node_red.json) → InfluxDB bucket: agro_iot_data (:8086)
  → Fase4: Node-RED (flow_node_red_fase4.json) → InfluxDB bucket: agro_iot_indicadores
  → Fase5: servicio_alertas.py → Email/SMS/WhatsApp/MQTT notifications
  → Fase6: Fase6_Analitica_Prediccion.ipynb → modelos_agroclimaticos_fase6.joblib
  → Fase7: Grafana dashboards (:3000)
```

**InfluxDB schema:**
- `agro_iot_data` (30d retention): raw sensor readings; measurement=`sensor_data`, tags=`parcela/cultivo/ubicacion/departamento/variable/unidad/sensor_id`
- `agro_iot_indicadores` (365d retention): derived indicators; measurement=`indicadores`, tags=`parcela/cultivo/ubicacion/departamento/indicador/unidad`

**ML models (`Fase6/modelos_agroclimaticos_fase6.joblib`):**
- Model A: Random Forest regression — predicts T_min, T_max, VPD, Precipitation for 1–3 days ahead
- Model B: Gradient Boosting classifier — probability of CRITICAL alert in next 48h

## Running the System

### Infrastructure (macOS/Homebrew)

```bash
brew services start mosquitto       # MQTT broker :1883
brew services start influxdb@2      # Time-series DB :8086
node-red                            # Data flows UI :1880
brew services start grafana         # Dashboards :3000
```

### Fase2 — Sensor Simulator

```bash
cd Fase2
python simulador_sensores.py --duracion 300        # Run for 5 minutes
python simulador_sensores.py --duracion 60 --max-mensajes 50
mosquitto_sub -h localhost -t "agricultura/#" -v   # Monitor messages
```

### Fase5 — Alert Service

```bash
cd Fase5
# Required env vars:
export INFLUX_TOKEN="..."
export SMTP_USER="administradorparcelasiscom@gmail.com"
export SMTP_PASSWORD="..."
export TWILIO_ACCOUNT_SID="..."
export TWILIO_AUTH_TOKEN="..."

python3 servicio_alertas.py --once --dry-run   # Test mode
python3 servicio_alertas.py                    # Production (runs every 60s)
```

### Fase6 — ML Model Training

```bash
cd Fase6
pip install pandas numpy scikit-learn matplotlib seaborn joblib jupyter
jupyter notebook Fase6_Analitica_Prediccion.ipynb
# Or headless:
jupyter nbconvert --execute --to notebook Fase6_Analitica_Prediccion.ipynb
```

### Fase7 — Populate Test Data

```bash
cd Fase7
python poblar_dia_completo.py   # Writes a full day of synthetic data to InfluxDB
```

## Key Files

| File | Purpose |
|------|---------|
| `Fase2/simulador_sensores.py` | Main MQTT publisher; 8 variables × 4 plots × 1 sensor each |
| `Fase2/dataset_agroclimatico_colombia.csv` | Source dataset: 52,757 records, 2007–2024, 8 locations |
| `Fase3/flow_node_red.json` | Basic Node-RED flow: MQTT → InfluxDB |
| `Fase4/flow_node_red_fase4.json` | Extended flow: adds VPD, Heat Index, GDD, Dew Point, ETo calculations |
| `Fase5/servicio_alertas.py` | Alert engine (~600 lines); reads InfluxDB, checks 24 thresholds, sends notifications |
| `Fase5/umbrales_agronomicos.yaml` | Declarative threshold config (24 rules, sourced from Cenicaña/FEDEARROZ/FAO-56) |
| `Fase6/modelos_agroclimaticos_fase6.joblib` | Serialized trained model bundle (8.7 MB) |
| `Fase7/datasource_influxdb.yaml` | Grafana provisioning: InfluxDB datasource |
| `Fase7/dashboards_provisioning.yaml` | Grafana provisioning: auto-load dashboards |
| `CommandsToExecuteSISCOM.txt` | Quick-reference command list with real credentials |
| `Proyecto_Consolidado.ipynb` | Master notebook summarizing all phases |

## Agronomic Context

- **Crops:** Sugarcane (Valle del Cauca) and Rice (Tolima, Casanare)
- **Monitored variables (8/location):** air temp, soil temp, relative humidity, solar radiation, wind speed, precipitation, soil humidity, soil pH
- **Derived indicators (Fase4):** VPD, Heat Index (HI), Dew Point (DP), Growing Degree Days (GDD), Reference Evapotranspiration (ETo/Hargreaves)
- **Alert tiers:** INFO / WARNING / CRITICAL with 30-minute anti-spam cooldown per threshold

## Environment Variables

All credentials are in `CommandsToExecuteSISCOM.txt`. The key ones:

```bash
export INFLUX_URL="http://localhost:8086"
export INFLUX_ORG="agricultura"
export INFLUX_BUCKET="agro_iot_data"
export INFLUX_BUCKET_IND="agro_iot_indicadores"
export INFLUX_TOKEN="<token from InfluxDB UI>"
```
