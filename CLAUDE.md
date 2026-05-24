# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Sistema de Monitoreo IoT y Analítica Agroclimática — an end-to-end IoT pipeline for agricultural monitoring of Colombian crops (sugarcane in Valle del Cauca, rice in Tolima/Casanare), built as an academic project at Universidad ICESI.

The project is organized into seven sequential phases (Fase 0–7), each building on the previous one.

## Architecture

```
CSV Dataset → Sensor Simulation → MQTT Broker → Node-RED Gateway → InfluxDB → Alert Service → Grafana
  (Fase 1)       (Fase 2)         (Mosquitto)     (Fase 3–4)                   (Fase 5)       (Fase 7)
                                                                               ML (Fase 6)
```

**Key components:**
- **`Fase2/simulador_sensores.py`** — simulates 32 virtual sensors (8 variables × 4 plots) publishing via MQTT using Python threads. Uses historical CSV data with noise injection and a configurable time acceleration factor (default 60×).
- **`Fase5/servicio_alertas.py`** — reads processed indicators from InfluxDB, evaluates agronomic thresholds from `umbrales_agronomicos.yaml`, and dispatches alerts via Email/SMS/WhatsApp/MQTT with cooldown protection.
- **`Fase3/flow_node_red.json`** / **`Fase4/flow_node_red_fase4.json`** — Node-RED flows that consume MQTT messages, transform them, calculate agroclimatic indicators (VPD, GDD, ETo per FAO-56), and write to InfluxDB.
- **`Fase7/`** — four Grafana dashboard JSON files plus provisioning YAML files (datasource and dashboard auto-loading).
- **`Fase5/umbrales_agronomicos.yaml`** — 288-line YAML defining per-crop, per-variable thresholds with severity levels (info/warning/critical) and notification channel routing.

**InfluxDB buckets:**
- `agro_iot_data` — raw sensor readings
- `agro_iot_indicadores` — processed agronomic indicators

**Documentation language:** Spanish throughout (code, comments, notebooks).

## Running the Stack

### Infrastructure (macOS/Homebrew)

```bash
# MQTT Broker
brew install mosquitto && brew services start mosquitto

# InfluxDB (UI at http://localhost:8086)
brew install influxdb && influxd

# Node-RED (UI at http://localhost:1880)
npm install -g --unsafe-perm node-red && node-red
# Install InfluxDB nodes via: Manage Palette → node-red-contrib-influxdb

# Grafana (UI at http://localhost:3000)
brew install grafana && brew services start grafana
cp Fase7/datasource_influxdb.yaml /opt/homebrew/etc/grafana/provisioning/datasources/
cp Fase7/dashboards_provisioning.yaml /opt/homebrew/etc/grafana/provisioning/dashboards/
```

### Python dependencies

```bash
# Fase 2
pip install paho-mqtt pandas

# Fase 5
pip install influxdb-client paho-mqtt PyYAML twilio
```

### Sensor Simulator (Fase 2)

```bash
# Run for 60 minutes, capped at 50 messages
python Fase2/simulador_sensores.py --duracion 60 --max-mensajes 50

# Monitor published messages
mosquitto_sub -h localhost -t "agricultura/#" -v
```

### Alert Service (Fase 5)

```bash
# Requires env vars: INFLUX_TOKEN, SMTP_USER, SMTP_PASSWORD (Gmail app password)
# Optional: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN for SMS/WhatsApp

python Fase5/servicio_alertas.py          # continuous mode
python Fase5/servicio_alertas.py --dry-run  # log only, no real notifications
python Fase5/servicio_alertas.py --once     # single evaluation cycle
```

## Key Design Decisions

- **Threading model in simulator:** one thread per sensor for independent, concurrent MQTT publishing.
- **Alert cooldown:** tracks last trigger time per alert to prevent notification spam; configured per variable in `umbrales_agronomicos.yaml`.
- **Evidence logging:** simulator appends all published messages to `evidencia_publicaciones.jsonl` (JSONL format) for audit trail.
- **Environment variable substitution:** `umbrales_agronomicos.yaml` supports `${VAR}` placeholders expanded at runtime in `servicio_alertas.py`.
- **Dry-run mode:** alert service logs notifications without sending — use for demos and testing thresholds.
- **InfluxDB tag strategy:** `parcela`, `cultivo`, `ubicacion` as tags for fast filtering; numeric sensor values as fields.
