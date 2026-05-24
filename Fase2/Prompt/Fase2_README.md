You are an expert in IoT systems, MQTT protocol, Python programming, and digital agriculture. I need you to help me develop PHASE 2 of my academic project. Below are the complete requirements.

## PHASE 2 — Simulation of Agricultural Sensors using MQTT Protocol and an IoT Gateway

### CONTEXT
In a real digital agriculture system, sensors installed in agricultural plots continuously capture agroclimatic variables such as temperature, soil humidity, solar radiation, or precipitation. These sensors send data through IoT networks to an analysis platform.

However, in an academic laboratory, physical sensors are not always available. Therefore, in this phase, we will build a simulator of agricultural sensors using Python, which will generate data based on real agroclimatic datasets downloaded from public repositories.

### SIMULATION ARCHITECTURE
The simulator will represent multiple sensors located in different agricultural plots and will send data via an MQTT Broker to an IoT Gateway. This will recreate a realistic IoT environment without the need for physical hardware.

**Data flow:**
```
Historical Dataset → Selection of most important variables → Row-by-row reading → IoT sensor simulation → Simulate in 4 plots → MQTT Broker → Data flow generation → IoT Gateway
```

**Each row of the dataset represents:** a sensor measurement of a variable for a specific plot, which should then be stored in the raw database as a time series.

### PHASE OBJECTIVE
Simulate IoT agricultural sensors that generate agroclimatic data based on real datasets and transmit them in real-time to an IoT platform using the MQTT protocol.

### LEARNING OUTCOMES
By the end of this phase, the student will be able to:
- Simulate IoT sensors using Python
- Generate continuous flows of agroclimatic data
- Publish data using an MQTT Broker (Mosquitto, EMQX, HiveMQ)
- Simulate up to 4 agricultural plots
- Understand how sensors transmit data in real IoT architectures

### SIMULATED AGROCLIMATIC VARIABLES
- Air temperature
- Soil temperature
- Relative humidity
- Solar radiation
- Wind speed
- Precipitation
- Soil pH

### TECHNOLOGIES TO USE

| Component | Technology | Download/Link |
|:---|:---|:---|
| Sensor simulation | Python or Google Colab | - |
| MQTT Broker | Eclipse Mosquitto | https://mosquitto.org/download/ |
| Python MQTT Library | Eclipse Paho MQTT Client | https://pypi.org/project/paho-mqtt/ |
| IoT Gateway | Node-RED | https://nodered.org/ |

### PROTOCOL EXPLANATION
**MQTT (Message Queuing Telemetry Transport)** is a lightweight protocol based on the publish/subscribe model, ideal for devices with limited resources and networks requiring very low latency. HTTP may also be used as an alternative.

### WIRELESS TECHNOLOGIES (for context)
In real scenarios, data is sent using physical layer wireless technologies such as: Bluetooth, Zigbee, Wi-Fi, or LoRaWAN. In this simulation, we will use MQTT over TCP/IP to emulate this behavior.

### SIMULATION SCENARIO
Simulate a sensor network distributed across 4 or more agricultural plots, representing different crops or terrain zones. Each plot will have sensors monitoring specific agroclimatic variables.

**Example:**
- Plot 1: Sugarcane
- Plot 2: Rice
- Plot 3: Coffee
- Plot 4: Oil palm

### STEP-BY-STEP IMPLEMENTATION

#### Step 1 — Load the public dataset downloaded from the internet
```python
import pandas as pd
df = pd.read_csv("soil_climate_crop_data.csv")
print(df.head())
print(df.shape)
print("Total records:", len(df))
```

#### Step 2 — Select sensor variables
Use the variables that most affect the growth and yield of each crop.
```python
sensor_df = df[[
    "Temperature",
    "Humidity", 
    "Rainfall",
    "Soil_pH"
]]
```

#### Step 3 — Configure MQTT client
```python
import paho.mqtt.client as mqtt

broker = "localhost"
port = 1883
topic = "agricultura/sensores"

client = mqtt.Client()
client.connect(broker, port)
```

**MQTT Message Structure (JSON example):**
```json
{
    "timestamp": "2026-04-20 18:45:00",
    "parcela": "parcela_1",
    "temperature_air": 28.5,
    "humidity": 70,
    "precipitation": 2.1,
    "soil_ph": 6.5
}
```

**IoT Gateway (Node-RED) role:**
```
Reception of MQTT messages → Data processing → Sending to database
```

#### Step 4 — Row-by-row reading of the dataset
```python
import datetime

def sensor_simulator(row, parcela):
    sensor_data = {
        "timestamp": str(datetime.datetime.now()),
        "parcela": parcela,
        "temperature_air": row["Temperature"],
        "humidity": row["Humidity"],
        "precipitation": row["Rainfall"],
        "soil_ph": row["Soil_pH"]
    }
    return sensor_data
```

#### Step 5 — Simulate sensor transmission
Iterate through the dataset as if it were a data stream.
```python
import time

for index, row in sensor_df.iterrows():
    data = sensor_simulator(row, "parcela_1")
    print(data)
    time.sleep(1)
```
*Note: `time.sleep(1)` simulates a sensor sending data every second. The sending frequency depends on the monitored variable and the crop type.*

#### Step 6 — Simulate the sensor network across multiple plots
In an agricultural farm, there are multiple plots with independent sensors.
```python
import json
import time

parcelas = ["parcela_1", "parcela_2", "parcela_3", "parcela_4"]

for index, row in sensor_df.iterrows():
    for parcela in parcelas:
        sensor_data = sensor_simulator(row, parcela)
        payload = json.dumps(sensor_data)
        client.publish(topic, payload)
        print("Data sent:", payload)
        time.sleep(1)
```
*Each message represents a sensor reading sent to the MQTT broker.*

#### Step 7 — Generate simulated IoT dataset
Store the data generated by the sensors.
```python
simulated_data = []

for index, row in sensor_df.iterrows():
    data = sensor_simulator(row, "parcela_1")
    simulated_data.append(data)

simulated_df = pd.DataFrame(simulated_data)
simulated_df.to_csv("iot_sensor_data.csv", index=False)
```

### DELIVERABLE FOR PHASE 2

The student must submit a **Python Notebook or script** that includes:

1. **Python script of the sensor simulator** (complete, runnable code)
2. **Evidence of MQTT message publication** (screenshots or logs showing messages being published)
3. **Screenshot of the MQTT broker receiving messages** (e.g., Mosquitto console or subscriber client output)
4. **Simulation of at least 4 agricultural plots** (code clearly showing 4 or more plots)
5. **Data flow generation** (continuous stream of simulated sensor data)

### ADDITIONAL NOTES

- The sending frequency (time.sleep value) can be adjusted: 0.5 to 5 seconds for simulation
- The broker address "localhost" assumes Mosquitto is installed locally
- If using an online broker, replace "localhost" with the actual broker IP or hostname
- The topic structure can be more specific, e.g., "agricultura/parcela_1/temperatura" for granular subscriptions

### YOUR TASK

Based on the information above, please:

1. Provide a complete, production-ready Python script that implements the sensor simulator
2. Include clear comments explaining each part of the code (in Spanish, as the deliverable must be in Spanish)
3. Explain how to install and run Eclipse Mosquitto on macOS
4. Show how to verify that MQTT messages are being published correctly (e.g., using mosquitto_sub)
5. Explain how to modify the script for different datasets (handle different column names)
6. Provide instructions for running the simulator and capturing evidence (screenshots, logs)

### LANGUAGE REQUIREMENT (IMPORTANT)

**ALL EXPLANATIONS, CODE COMMENTS, AND DOCUMENTATION MUST BE IN SPANISH.**

The Python code itself can remain in English (keywords, variable names), but all comments, markdown descriptions, and explanations MUST be written in Spanish.

Start your response with "# FASE 2: Simulación de sensores agrícolas con MQTT" and include all the deliverables listed above.

**REMEMBER: All deliverables must be in Spanish.**
