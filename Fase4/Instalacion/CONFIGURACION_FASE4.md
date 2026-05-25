# Configuración de la Fase 4 — Procesamiento en tiempo real

Esta guía explica cómo desplegar el pipeline de procesamiento de la Fase 4 sobre la infraestructura ya instalada en la Fase 3 (Mosquitto + Node-RED + InfluxDB v2).

> **Prerequisito:** la Fase 3 debe estar operativa. Si aún no, consulta `INSTALACION_INFLUXDB_NODERED.md` de la Fase 3.

---

## 1. Cambios sobre la infraestructura de Fase 3

| Componente | Fase 3 | Fase 4 |
|---|---|---|
| Mosquitto | localhost:1883 | sin cambios |
| Node-RED | flow simple (3 etapas) | flow ampliado (5 etapas) |
| InfluxDB v2 | 1 bucket: `agro_iot_data` | **2 buckets**: `agro_iot_data` + `agro_iot_indicadores` |

El segundo bucket separa las **mediciones limpias** (las mismas de Fase 3, pero con metadatos enriquecidos) de los **indicadores calculados en tiempo real** (Heat Index, VPD, ETo, etc.). Esto facilita:

- Aplicar políticas de retención distintas (datos crudos = 30 días, indicadores = 1 año).
- Que la Fase 5 (alertas) consulte un único bucket compacto sin atravesar millones de mediciones.
- Visualizar las dos capas en dashboards separados de Grafana (Fase 7).

---

## 2. Crear el bucket de indicadores en InfluxDB

### 2.1 Desde la UI

1. Abre `http://localhost:8086`.
2. Ve a **Load Data → Buckets → CREATE BUCKET**.
3. Configura:
   - **Name**: `agro_iot_indicadores`
   - **Delete data older than**: `365 days` (1 año — los indicadores son más valiosos a largo plazo).
4. **CREATE**.

### 2.2 O desde el CLI

```bash
# Asegúrate de tener el config activo de la Fase 3:
influx config list

# Crear el bucket
influx bucket create \
  --name agro_iot_indicadores \
  --org agricultura \
  --retention 365d

# Verificar
influx bucket list
# Deben aparecer ambos: agro_iot_data y agro_iot_indicadores
```

### 2.3 Verificar/extender permisos del token de Node-RED

Si el token de Node-RED creado en la Fase 3 solo tenía permisos sobre `agro_iot_data`, hay que actualizarlo:

1. UI → **Load Data → API Tokens**.
2. **Generate API Token → Custom API Token**.
3. **Description**: `node-red-gateway-f4`.
4. Marcar **Read + Write** sobre **ambos** buckets (`agro_iot_data` y `agro_iot_indicadores`).
5. **Save**, copiar el token.

---

## 3. Desplegar el flow ampliado en Node-RED

### 3.1 Importar el nuevo flow

1. Abre `http://localhost:1880`.
2. Menú ☰ → **Import** → selecciona `flow_node_red_fase4.json`.
3. **Import** → aparecerá una nueva pestaña **"Fase 4 — Procesamiento en tiempo real"**.

> El flow de Fase 3 puede coexistir en otra pestaña, pero te recomiendo desactivar ese flow (clic derecho sobre la pestaña → **Disable**) para evitar duplicación de mensajes en InfluxDB, ya que el flow de Fase 4 también escribe al bucket `agro_iot_data`.

### 3.2 Configurar los dos nodos InfluxDB Out

El flow trae **dos** servidores InfluxDB configurados (uno por bucket). Para cada uno:

1. Doble clic sobre **"InfluxDB → sensor_data"** y **"InfluxDB → indicadores"**.
2. Clic en el lápiz junto a **Server**.
3. Pegar el token de Node-RED (paso 2.3).
4. Verificar: **Version=2.0**, **URL=http://localhost:8086**, **Organization=agricultura**.
5. Cada nodo apunta a su bucket correspondiente (ya pre-configurado).

### 3.3 Deploy

Clic en **Deploy** (botón rojo). Los nodos MQTT In y los dos InfluxDB Out deben mostrar **● connected** en verde.

---

## 4. Verificación rápida

### 4.1 Activar el simulador

```bash
cd /ruta/a/fase2
python simulador_sensores.py --duracion 120
```

### 4.2 En el panel Debug de Node-RED

Habilita el nodo "Debug — indicadores" y deberías ver mensajes como:

```json
[
  { "payload": [{"indice_calor": 24.51}, {"parcela":"parcela_1","cultivo":"caña","indicador":"indice_calor","unidad":"°C", ...}] },
  { "payload": [{"punto_rocio": 20.31}, {"parcela":"parcela_1","cultivo":"caña","indicador":"punto_rocio","unidad":"°C", ...}] },
  { "payload": [{"vpd": 0.596},      {"parcela":"parcela_1","cultivo":"caña","indicador":"vpd","unidad":"kPa", ...}] }
]
```

### 4.3 Consulta en InfluxDB

```flux
from(bucket: "agro_iot_indicadores")
  |> range(start: -10m)
  |> filter(fn: (r) => r._measurement == "indicadores")
  |> group(columns: ["indicador", "parcela"])
  |> last()
```

Deberías ver al menos 4 parcelas × 5 indicadores = 20 filas.

---

## 5. Etapas de procesamiento implementadas

| # | Etapa | Implementación | Salida |
|---|---|---|---|
| 1 | **Limpieza** | function Node-RED: valida tipos, rangos físicos, deduplica | mensaje válido o `null` |
| 2 | **Transformación** | function Node-RED: normaliza unidades, enriquece con metadata, ISO timestamps | mensaje enriquecido |
| 3 | **Indicadores agroclimáticos** | function Node-RED: Heat Index, Dew Point, VPD, GDD | array de indicadores |
| 4 | **Variables derivadas** | function Node-RED: ETo Hargreaves (FAO-56) | array de derivadas |
| 5 | **Persistencia** | dos nodos InfluxDB Out a buckets distintos | persistido en TSDB |

---

## 6. Indicadores calculados — detalles agronómicos

### 6.1 Índice de calor (Heat Index)

**Fórmula:** ecuación de Rothfusz / NWS (Steadman 1979).  
**Variables requeridas:** T° aire, HR%.  
**Significado:** sensación térmica considerando humedad. Crítico para trabajadores en campo y para identificar olas de calor.  
**Unidad:** °C.

### 6.2 Punto de rocío (Dew Point)

**Fórmula:** Magnus-Tetens con coeficientes a=17.625, b=243.04 °C.  
**Significado:** temperatura a la cual el aire se satura. Si T_min se acerca al DP, hay condensación → riesgo fitosanitario (roya en caña, Pyricularia en arroz).  
**Unidad:** °C.

### 6.3 Déficit de presión de vapor (VPD)

**Fórmula:** FAO-56 ecuaciones 11-12: `VPD = es(T) − es(T) × RH/100`, donde `es(T) = 0.6108 × exp(17.27T/(T+237.3))`.  
**Significado:** medida directa de demanda atmosférica de agua. **El indicador #1 de estrés hídrico foliar.** Rangos agronómicos:

- 0.4-1.0 kPa: óptimo
- 1.0-1.6 kPa: estrés moderado
- > 1.6 kPa: estrés severo, los estomas se cierran y se detiene la fotosíntesis

**Unidad:** kPa.

### 6.4 Grados-día de crecimiento (GDD)

**Fórmula:** `GDD = max(0, T_media − T_base)`.  
**Variables requeridas:** T° media (en versiones siguientes: T_max, T_min).  
**T_base por cultivo:** 18 °C para caña (Cenicaña), 10 °C para arroz (FEDEARROZ).  
**Significado:** indicador de acumulación térmica que predice fenología (floración, madurez).  
**Unidad:** °C·día (acumulado por la Fase 5 vía task Flux).

### 6.5 Evapotranspiración de referencia (ETo) — FAO-56 Hargreaves

**Fórmula:** `ETo = 0.0023 × (T_mean + 17.8) × √(T_max − T_min) × Ra × 0.408`.

- `Ra` = radiación extraterrestre (~36 MJ/m²/día para latitud ecuatorial promedio anual).
- `0.408` = factor de conversión MJ/m²/día → mm/día.

**Significado:** demanda hídrica de un cultivo de referencia (pasto). Multiplicado por `Kc` (coeficiente de cultivo) da la demanda real:

- Caña en pleno desarrollo: `Kc ≈ 1.25` → ETc real ≈ 5.5 mm/día.
- Arroz inundado: `Kc ≈ 1.20` → ETc real ≈ 5.3 mm/día.

**Unidad:** mm/día.

---

## 7. Por qué dos buckets separados

| Aspecto | `agro_iot_data` | `agro_iot_indicadores` |
|---|---|---|
| Cardinalidad | alta (32 sensores × 4 parcelas × frecuencias varias) | baja (~5 indicadores × 4 parcelas) |
| Volumen diario | ~50.000 puntos | ~5.000 puntos |
| Frecuencia consulta (Fase 5) | rara (datos crudos) | constante (alertas) |
| Retención recomendada | 30 días | 365 días |
| Costo computacional de queries | alto | bajo |

Mantenerlos separados permite a la Fase 5 hacer queries de alertas sobre un bucket pequeño y rápido, sin atravesar el bucket de mediciones crudas.

---

## 8. Solución de problemas

| Síntoma | Causa probable | Solución |
|---|---|---|
| El nodo InfluxDB Out de indicadores marca "unauthorized" | Token sin permisos al nuevo bucket | Crear/actualizar token con R/W sobre ambos buckets |
| El bucket `agro_iot_indicadores` no aparece | Bucket no creado todavía | Paso 2 de esta guía |
| Los indicadores no se calculan (debug vacío) | T° y RH no llegan en la misma ventana de 10 min | Verificar que el simulador esté publicando ambas variables; revisar el cache de flow `cache_parcelas` |
| Solo se calculan algunos indicadores | Comportamiento correcto: cada indicador requiere variables específicas frescas | OK — los indicadores aparecen progresivamente |
| Mensajes "fuera de rango físico" en debug | El simulador publicó un valor anómalo (poco común) | OK — la etapa de limpieza está cumpliendo su función |

---

## 9. Próxima fase (Fase 5)

Los indicadores almacenados en `agro_iot_indicadores` son la **base directa** de las alertas de la Fase 5:

| Indicador (Fase 4) | Umbral de alerta (Fase 5) | Alerta |
|---|---|---|
| `vpd` | > 1.6 kPa sostenido 1 h | Estrés hídrico severo — programar riego |
| `indice_calor` | > 35 °C | Riesgo térmico en cultivo y trabajadores |
| `punto_rocio` | T_min − DP < 2 °C | Condensación nocturna — riesgo de hongos |
| `eto_hargreaves` | > 6 mm/día | Demanda hídrica alta — revisar lámina/turno |
| `gdd_instantaneo` | acumulado por etapa fenológica | Fase fenológica esperada del cultivo |

La Fase 5 consultará estos indicadores con tasks Flux y disparará notificaciones (email, SMS, WhatsApp).
