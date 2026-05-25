# FASE 4 — Procesamiento de datos IoT en tiempo real

Pipeline ampliado sobre Node-RED + InfluxDB que añade **limpieza**, **transformación**, **cálculo de indicadores agroclimáticos** y **variables derivadas (ETo)** sobre los datos que el simulador (Fase 2) envía vía MQTT a Mosquitto y persiste en InfluxDB (Fase 3).

---

## Archivos entregados

| Archivo | Propósito |
|---|---|
| `Fase4_Procesamiento_Pipeline.ipynb` | Notebook Jupyter con las 4 etapas implementadas en Python, procesamiento batch del histórico y persistencia de indicadores en InfluxDB. |
| `flow_node_red_fase4.json` | Flow Node-RED ampliado para importar (15 nodos: MQTT In + 4 funciones de procesamiento + 2 nodos de preparación + 2 outputs Influx + debug). |
| `CONFIGURACION_FASE4.md` | Guía paso a paso para crear el segundo bucket en InfluxDB y desplegar el flow. |
| `dataset_agroclimatico_colombia.csv` | Dataset de Fase 1 (necesario para el procesamiento batch). |
| `diagrama_arquitectura_fase4.png` | Diagrama completo del pipeline de 5 etapas. |
| `evidencia_nodered_flow_fase4.png` | Captura simulada del flow Node-RED desplegado. |
| `README.md` | Este archivo. |

---

## Inicio rápido (3 pasos)

### Paso 1 — Crear el segundo bucket en InfluxDB

```bash
# Asegúrate de tener el config activo de Fase 3
influx bucket create \
  --name agro_iot_indicadores \
  --org agricultura \
  --retention 365d
```

Y actualizar (o crear nuevo) un token con permisos R/W sobre **ambos** buckets (`agro_iot_data` + `agro_iot_indicadores`).

### Paso 2 — Importar el flow ampliado en Node-RED

1. Abrir Node-RED en `http://localhost:1880`.
2. Menú ☰ → **Import** → seleccionar `flow_node_red_fase4.json`.
3. Configurar el token en los dos nodos `InfluxDB Out`.
4. **Deploy**.

> Si el flow de Fase 3 está activo, deshabilítalo (clic derecho en la pestaña → Disable) para evitar duplicación.

### Paso 3 — Activar el simulador y verificar

```bash
# Terminal 1
cd /ruta/a/fase2 && python simulador_sensores.py --duracion 300

# Terminal 2 (notebook)
export INFLUX_TOKEN="<tu-token>"
jupyter notebook Fase4_Procesamiento_Pipeline.ipynb
```

---

## Las 5 etapas del pipeline

| # | Etapa | Implementación | Responsabilidad |
|---|---|---|---|
| 1 | **Limpieza** | function Node-RED | Valida estructura, rangos físicos, deduplica |
| 2 | **Transformación** | function Node-RED | Normaliza unidades, enriquece con metadata, ISO timestamps |
| 3 | **Indicadores agroclimáticos** | function Node-RED | Calcula HI, DP, VPD, GDD usando cache de últimas variables |
| 4 | **Variables derivadas** | function Node-RED | Calcula ETo (Hargreaves FAO-56) |
| 5 | **Persistencia** | 2 nodos InfluxDB Out | Escribe a `agro_iot_data` (raw) y `agro_iot_indicadores` (derivados) |

---

## Indicadores agroclimáticos implementados

| Indicador | Fórmula | Unidad | Significado agronómico |
|---|---|---|---|
| **Heat Index (HI)** | NWS Steadman/Rothfusz | °C | Sensación térmica con humedad |
| **Punto de rocío (DP)** | Magnus-Tetens | °C | Riesgo de condensación nocturna → hongos |
| **VPD** | FAO-56: 0.6108·exp(17.27T/(T+237.3))·(1−RH/100) | kPa | Estrés hídrico atmosférico foliar |
| **GDD** | max(0, T − T_base) | °C·día | Acumulación térmica fenológica |
| **ETo** | Hargreaves FAO-56: 0.0023·(T+17.8)·√(Tmax−Tmin)·Ra·0.408 | mm/día | Demanda hídrica del cultivo de referencia |

### T_base por cultivo

- **Caña de azúcar**: 18°C (Cenicaña RMA)
- **Arroz**: 10°C (FEDEARROZ-AMTEC)

### Rangos VPD para interpretación

- **0.4-1.0 kPa**: óptimo (sin estrés)
- **1.0-1.6 kPa**: estrés moderado
- **>1.6 kPa**: estrés severo, los estomas se cierran, fotosíntesis detenida

---

## Esquema de datos en InfluxDB

### Bucket `agro_iot_data` (raw limpio, retención 30d)

```
measurement:  sensor_data
tags:         parcela, cultivo, ubicacion, departamento, variable, unidad, sensor_id
fields:       <nombre_variable>: float    (campo dinámico, igual que Fase 3)
```

### Bucket `agro_iot_indicadores` (derivados, retención 365d)

```
measurement:  indicadores
tags:         parcela, cultivo, ubicacion, departamento, indicador, unidad
fields:       <nombre_indicador>: float
```

Ejemplos de `nombre_indicador`:

- `indice_calor`
- `punto_rocio`
- `vpd`
- `gdd_instantaneo`
- `eto_hargreaves`

---

## Cumplimiento del entregable

El PDF de la Fase 4 pide un **pipeline funcional que incluya**:

| Componente | Cumplido | Implementación |
|---|---|---|
| **Data Ingestion** | ✅ | MQTT In + Etapa 1 (limpieza) en Node-RED |
| **Data Processing** | ✅ | Etapas 2-4 (transformación, indicadores, derivadas) en Node-RED |
| **Data Storage** | ✅ | 2 nodos InfluxDB Out → 2 buckets organizados por capa de datos |

---

## Validación numérica de los indicadores

Aplicando las fórmulas a las temperaturas corregidas de Fase 1:

| Parcela | T° | HR | HI | DP | VPD | GDD | ETo |
|---|---|---|---|---|---|---|---|
| Palmira (caña) | 23.97°C | 80% | 24.51°C | 20.31°C | 0.596 kPa | 5.97 | 4.462 mm/día |
| Candelaria (caña) | 24.17°C | 76% | 24.63°C | 19.67°C | 0.723 kPa | 6.17 | 4.484 mm/día |
| Espinal (arroz) | 27.34°C | 73% | 29.75°C | 22.07°C | 0.982 kPa | 17.34 | 4.822 mm/día |
| Yopal (arroz) | 26.70°C | 70% | 28.36°C | 20.77°C | 1.051 kPa | 16.70 | 4.754 mm/día |

**Interpretación:** Todos los valores son agronómicamente consistentes con la literatura tropical colombiana. VPD entre 0.6-1.0 kPa (rango óptimo). ETo ~4.5 mm/día (consistente con tablas FAO para latitud 4°N). GDD mucho mayor en arroz por T_base más baja.

---

## Por qué este diseño facilita la Fase 5 (alertas)

La Fase 5 tendrá que detectar condiciones críticas como:

- **Estrés hídrico severo**: `vpd > 1.6 kPa` sostenido 1 h
- **Estrés térmico**: `indice_calor > 35 °C`
- **Riesgo fitosanitario nocturno**: `T_aire − punto_rocio < 2 °C` (condensación en hojas)
- **Demanda hídrica anómala**: `eto_hargreaves > 6 mm/día`

Gracias al bucket separado `agro_iot_indicadores`:

- La Fase 5 consulta un bucket pequeño y rápido (no atraviesa millones de mediciones crudas).
- Los umbrales se aplican sobre valores ya calculados, no sobre fórmulas embebidas en cada alerta.
- La separación raw/derivados es estándar en arquitecturas IoT productivas (Lambda/Kappa).

---

## Próxima fase

**Fase 5 — Definición de umbrales agronómicos y generación de alertas:** se construirán tasks Flux que consulten `agro_iot_indicadores` periódicamente y disparen notificaciones por Email, SMS o WhatsApp cuando los umbrales se violen.
