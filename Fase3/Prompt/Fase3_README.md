# Phase 3 — IoT Data Ingestion and Storage in Time Series Database

## Overview

In digital agriculture systems, IoT sensors generate continuous time-series data about agroclimatic variables such as air temperature, relative humidity, precipitation, solar radiation, and soil pH. This data must be stored in a database that enables historical analysis, real-time monitoring, and alert generation.

In this phase, students simulate the IoT data ingestion process, where raw data transmitted by sensors and sent to the Gateway will be captured and stored in a **Time Series Database (TSDB)**.

---

## Learning Outcomes

By the end of this phase, students will be able to:

- Simulate an IoT data ingestion pipeline
- Integrate sensors with an MQTT broker
- Process data in an IoT Gateway
- Store data in a time series database

---

## Data Flow Architecture

```
Simulated Sensors (Python) → MQTT Broker (Mosquitto) → IoT Gateway (Node-RED) → Time Series Database (InfluxDB)
```

---

## Deliverables

Students must submit:

| # | Deliverable |
|:---|:---|
| 1 | Screenshot of the implemented Node-RED flow |
| 2 | MQTT Broker configuration (Mosquitto) |
| 3 | Database created in InfluxDB (evidence) |
| 4 | Evidence of data storage |
| 5 | Query showing stored records |

---

## Technologies Used

| Component | Technology | Description |
|:---|:---|:---|
| **MQTT Broker** | Eclipse Mosquitto | Manages communication between sensors and gateway |
| **IoT Gateway** | Node-RED | Open-source tool for integrating devices, APIs, and databases |
| **Time Series DB** | InfluxDB | Optimized for IoT, industrial monitoring, climate, and agricultural sensors |

### Download Links

- **Eclipse Mosquitto**: [https://mosquitto.org/download/](https://mosquitto.org/download/)
- **Node-RED**: [https://nodered.org/](https://nodered.org/)
- **InfluxDB**: [https://www.influxdata.com/downloads/](https://www.influxdata.com/downloads/)

---

## Step-by-Step Implementation Guide

### Step 1 — Install InfluxDB

Follow the installation guide for your operating system from the official website.

**Verification commands:**

```bash
# Check if InfluxDB is running
influxd

# Access the web interface
# Open: http://localhost:8086
```

---

### Step 2 — Create Database (Organization and Bucket)

1. Open InfluxDB web interface at `http://localhost:8086`
2. Create a new **Organization** named: `agricultura`
3. Create a new **Bucket** named: `agro_iot_data`

---

### Step 3 — Create API Access Token

1. In InfluxDB, navigate to **Data → API Tokens**
2. Click **Generate Token**
3. Save the generated token — you will need it for Node-RED connection

---

### Step 4 — Install Node-RED

```bash
# Install Node-RED globally
npm install -g --unsafe-perm node-red

# Start Node-RED
node-red

# Access web interface
# Open: http://localhost:1880
```

---

### Step 5 — Install InfluxDB Nodes in Node-RED

1. Open Node-RED at `http://localhost:1880`
2. Go to **Menu → Manage Palette**
3. Search for and install: **`node-red-contrib-influxdb`**

---

### Step 6 — Create the Data Ingestion Flow

Build the following flow in Node-RED:

```
MQTT Input → JSON Parser → Data Transformation → InfluxDB Output
```

---

### Step 7 — Configure MQTT Input Node

Add an **MQTT Input** node and configure:

| Parameter | Value |
|:---|:---|
| **Broker** | `localhost` |
| **Port** | `1883` |
| **Topic** | `agricultura/sensores` |
| **QoS** | `1` |

This node will receive data from the Python sensor simulator.

---

### Step 8 — Add JSON Parser Node

Add a **JSON** node to transform the incoming MQTT message from string to JSON object.

---

### Step 9 — Add Data Transformation Function Node

Add a **Function** node with the following JavaScript code to structure data for InfluxDB:

```javascript
msg.payload = [
    {
        measurement: "sensor_data",
        tags: {
            parcela: msg.payload.parcela,
            cultivo: msg.payload.cultivo,
            ubicacion: msg.payload.ubicacion
        },
        fields: {
            temperature_air: parseFloat(msg.payload.temperature_air),
            humidity: parseFloat(msg.payload.humidity),
            precipitation: parseFloat(msg.payload.precipitation),
            soil_ph: parseFloat(msg.payload.soil_ph),
            solar_radiation: parseFloat(msg.payload.solar_radiation) || 0,
            wind_speed: parseFloat(msg.payload.wind_speed) || 0
        },
        timestamp: new Date(msg.payload.timestamp).toISOString()
    }
];

return msg;
```

**What this code does:**
- `measurement`: The name of the measurement (like a table in SQL)
- `tags`: Indexed metadata for fast filtering (parcela, cultivo, ubicacion)
- `fields`: The actual numeric data values
- `timestamp`: The time of the measurement

---

### Step 10 — Configure InfluxDB Output Node

Add an **InfluxDB Out** node and configure:

| Parameter | Value |
|:---|:---|
| **Server** | `http://localhost:8086` |
| **Organization** | `agricultura` |
| **Bucket** | `agro_iot_data` |
| **Token** | `[YOUR_GENERATED_TOKEN]` |

---

### Step 11 — Deploy the Flow

Click the **Deploy** button in Node-RED.

Your Gateway is now storing data continuously as messages arrive from the MQTT broker.

---

### Step 12 — Verify Stored Data in InfluxDB

1. Open InfluxDB web interface at `http://localhost:8086`
2. Go to **Data Explorer**
3. Run the following Flux query:

```flux
from(bucket: "agro_iot_data")
  |> range(start: -10m)
  |> filter(fn: (r) => r._measurement == "sensor_data")
  |> yield(name: "ultimos_datos")
```

Alternatively, a simpler query:

```flux
from(bucket: "agro_iot_data")
  |> range(start: -1h)
```

You should see the data sent by the sensors appearing in the results.

---

## Example MQTT Message (From Python Simulator)

```json
{
    "timestamp_real": "2025-06-04T13:30:00.000Z",
    "timestamp_simulado": "2024-01-15T14:00:00.000Z",
    "parcela": "parcela_1",
    "cultivo": "caña",
    "ubicacion": "Palmira_VAC",
    "temperature_air": 24.5,
    "humidity": 75.2,
    "precipitation": 0.0,
    "soil_ph": 6.8,
    "solar_radiation": 18.3,
    "wind_speed": 2.1
}
```

---

## Troubleshooting

| Problem | Solution |
|:---|:---|
| Node-RED cannot connect to MQTT | Verify Mosquitto is running: `mosquitto -v` |
| InfluxDB connection fails | Check token is correct and bucket name matches |
| No data appears in InfluxDB | Check Node-RED debug tab for errors; verify JSON structure |
| "Connection refused" on port 1883 | Install/start Mosquitto: `sudo systemctl start mosquitto` (Linux) or install via Homebrew (macOS) |

---

## Deliverable Summary Checklist

| # | Deliverable | Status |
|:---|:---|:---|
| 1 | Screenshot of Node-RED flow | ☐ |
| 2 | Mosquitto MQTT broker configuration | ☐ |
| 3 | InfluxDB database created (screenshot) | ☐ |
| 4 | Evidence of data storage (InfluxDB data explorer) | ☐ |
| 5 | Query showing stored records (screenshot) | ☐ |

---

## Next Steps

After completing this phase, you will be ready for:

- **Phase 4**: Real-time data processing

---

**Project:** IoT Monitoring System for Digital Agriculture  
**Crops:** Sugarcane (Valle del Cauca) and Rice (Tolima, Casanare, Meta)  
**Institution:** Universidad ICESI — Systems and Communications I