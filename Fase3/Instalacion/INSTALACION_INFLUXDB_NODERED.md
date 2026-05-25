# Instalación de InfluxDB v2 + Node-RED en macOS — Guía paso a paso

> Esta guía cubre la instalación local de los dos componentes principales de la Fase 3 sobre macOS (Apple Silicon e Intel) usando Homebrew. Asume que ya tienes **Eclipse Mosquitto** corriendo desde la Fase 2 (si no, ver `INSTALACION_MOSQUITTO.md`).

---

## Stack final de la Fase 3

```
Simulador Python (Fase 2)
        │ MQTT publish
        ▼
Eclipse Mosquitto         (broker MQTT en localhost:1883)
        │ MQTT subscribe
        ▼
Node-RED                  (gateway IoT en localhost:1880)
        │ HTTP write
        ▼
InfluxDB v2               (base de datos de series de tiempo en localhost:8086)
```

---

## 1. Prerrequisitos

- macOS 11+ (Big Sur o superior).
- **Homebrew** instalado (`brew --version` debe responder).
- **Mosquitto** corriendo en `localhost:1883` desde la Fase 2.
- **Node.js 18 LTS o superior** (Node-RED lo requiere).

Verificar Node.js:

```bash
node --version
# v20.x.x  (cualquier versión 18+ está bien)
```

Si no tienes Node.js o tienes una versión muy antigua:

```bash
brew install node
```

---

## 2. Instalación de InfluxDB v2

> **Importante:** desde mediados de 2025, el comando `brew install influxdb` instala **InfluxDB 3** (alias `influxdb@3`), que tiene un modelo de configuración diferente al que pide el documento del laboratorio. Para esta fase necesitamos **InfluxDB 2** explícitamente. Esto significa usar `brew install influxdb@2`.

### 2.1 Instalar el servidor InfluxDB v2

```bash
brew update
brew install influxdb@2
```

La fórmula `influxdb@2` es **keg-only** (no se enlaza al `$PATH` por defecto para evitar conflictos con InfluxDB 3). Hay dos opciones:

**Opción A — Iniciarlo como servicio (recomendado):**

```bash
brew services start influxdb@2
```

**Opción B — Ejecutarlo en primer plano (útil para depurar):**

```bash
# Apple Silicon
/opt/homebrew/opt/influxdb@2/bin/influxd
# Intel
/usr/local/opt/influxdb@2/bin/influxd
```

Verifica que está escuchando en el puerto **8086**:

```bash
lsof -iTCP:8086 -sTCP:LISTEN
# COMMAND   PID USER ...    NODE NAME
# influxd  1234 user ...   TCP localhost:8086 (LISTEN)
```

### 2.2 Instalar el cliente CLI `influx`

```bash
brew install influxdb-cli
```

Verifica:

```bash
influx version
# Influx CLI 2.x.x ...
```

### 2.3 Configuración inicial vía interfaz web

1. Abrir en el navegador: **http://localhost:8086**
2. Hacer clic en **"Get Started"**.
3. Llenar el formulario inicial:
   - **Username**: `admin` (o tu usuario)
   - **Password**: una contraseña fuerte (anótala)
   - **Initial Organization Name**: `agricultura`
   - **Initial Bucket Name**: `agro_iot_data`
4. Hacer clic en **"Continue"**.

Al finalizar, InfluxDB muestra un **Operator Token**. Cópialo y guárdalo a un sitio seguro.

> ⚠ **Crítico:** desde InfluxDB OSS 2.9.0 los tokens se hashean en disco al primer arranque, por lo que **después de cerrar la pantalla del setup ya no podrás recuperar el token original**. Si te lo pierdes, tendrás que generar uno nuevo desde la sección **Load Data → API Tokens**.

### 2.4 Crear un token específico para Node-RED (recomendado)

Por seguridad, no usar el Operator Token directamente. Crear uno con permisos limitados al bucket `agro_iot_data`:

1. En la UI: **Load Data → API Tokens → Generate API Token → Custom API Token**.
2. **Description**: `node-red-gateway`.
3. **Permissions**: marcar **Read** y **Write** solo sobre el bucket `agro_iot_data`.
4. **Save**, copiar el token y guardarlo en un sitio seguro.

Validar la configuración con el CLI:

```bash
influx config create --config-name local \
  --host-url http://localhost:8086 \
  --org agricultura \
  --token <TU_TOKEN_AQUI> \
  --active

influx bucket list
# Debe listar agro_iot_data
```

---

## 3. Instalación de Node-RED

### 3.1 Instalar globalmente vía npm

```bash
npm install -g --unsafe-perm node-red
```

Si te aparece un error de permisos, usa:

```bash
sudo npm install -g --unsafe-perm node-red
```

### 3.2 Iniciar Node-RED

```bash
node-red
```

La terminal mostrará algo como:

```
Welcome to Node-RED
===================
13 May 02:45:20 - [info] Node-RED version: v4.x.x
13 May 02:45:20 - [info] Server now running at http://127.0.0.1:1880/
```

Abrir en el navegador: **http://localhost:1880**

### 3.3 Iniciar Node-RED como servicio (opcional)

Para que arranque automáticamente al reiniciar el Mac, se recomienda usar `pm2`:

```bash
npm install -g pm2
pm2 start "$(which node-red)" --name node-red
pm2 save
pm2 startup
# Sigue las instrucciones que imprime para hacerlo persistente
```

### 3.4 Instalar el paquete `node-red-contrib-influxdb`

1. En Node-RED (http://localhost:1880), clic en el menú ☰ (arriba a la derecha) → **Manage palette**.
2. Pestaña **Install**.
3. Buscar: `node-red-contrib-influxdb`.
4. Clic en **Install** (versión 0.7.x o superior — soporta InfluxDB v2).
5. Esperar el mensaje de "Nodes added to palette".

Después de instalar, deberías ver tres nuevos nodos en el panel izquierdo bajo la categoría **storage**: `influxdb in`, `influxdb out`, `influxdb batch`.

---

## 4. Importar el flow listo del proyecto

En lugar de construir el flow nodo por nodo, este proyecto incluye el archivo **`flow_node_red.json`** que se puede importar directamente.

### 4.1 Importar el flow

1. En Node-RED, clic en el menú ☰ → **Import**.
2. Pestaña **select a file to import** → elegir `flow_node_red.json`.
3. Clic en **Import**.

Aparecerá una nueva pestaña llamada **"Fase 3 — Gateway IoT (Caña + Arroz)"** con 7 nodos conectados:

```
[MQTT In: agricultura/#] → [Filtrar sistema] → [Transformar] → [InfluxDB Out]
                            └→ [Debug raw]      └→ [Debug post]
```

### 4.2 Configurar el token de InfluxDB en el nodo

El flow se importa con todos los parámetros listos excepto el token (no se incluye por seguridad). Para configurarlo:

1. Doble clic sobre el nodo **"InfluxDB Out — sensor_data"**.
2. Clic en el ícono de lápiz junto a **Server** ("InfluxDB local (Fase 3)").
3. En **Token**, pegar el token de Node-RED creado en el paso 2.4.
4. Verificar:
   - **Version**: 2.0
   - **URL**: `http://localhost:8086`
   - **Organization**: `agricultura`
   - **Bucket**: `agro_iot_data`
5. Clic en **Update** → **Done**.

### 4.3 Desplegar (Deploy)

Clic en **Deploy** (botón rojo arriba a la derecha).

El nodo MQTT In debería mostrar el indicador **● connected** en verde, y el nodo InfluxDB Out también.

---

## 5. Verificar el flujo end-to-end

### 5.1 Iniciar el simulador de la Fase 2 en otra terminal

```bash
cd /ruta/a/tu/proyecto/fase2
python simulador_sensores.py --duracion 60 --max-mensajes 30
```

Mientras corre, en Node-RED:

- En el panel **Debug** (lateral derecho) deberías ver mensajes con la estructura post-transformación: un objeto con `payload` (array `[fields, tags]`) y `timestamp`.
- En el nodo **InfluxDB Out** deberías ver el indicador de actividad (puntos blancos).

### 5.2 Verificar los datos en InfluxDB

1. Abrir http://localhost:8086 → **Data Explorer**.
2. En el panel inferior, seleccionar la pestaña **Query Builder**:
   - **Bucket**: `agro_iot_data`
   - **Filter**: `_measurement` = `sensor_data`
   - **Time range**: `Past 5m`
3. Clic en **Submit**. Deberías ver una tabla con los datos llegando.

O alternativamente, en la pestaña **Script Editor**, ejecutar:

```flux
from(bucket: "agro_iot_data")
  |> range(start: -10m)
  |> filter(fn: (r) => r._measurement == "sensor_data")
  |> yield(name: "ultimos_datos")
```

### 5.3 Consultas útiles para evidencia

**Total de puntos en los últimos 10 minutos por parcela:**

```flux
from(bucket: "agro_iot_data")
  |> range(start: -10m)
  |> filter(fn: (r) => r._measurement == "sensor_data")
  |> group(columns: ["parcela"])
  |> count()
```

**Temperatura del aire promedio por parcela en la última hora:**

```flux
from(bucket: "agro_iot_data")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "sensor_data" and r._field == "temperatura_aire")
  |> group(columns: ["parcela"])
  |> mean()
```

**Series temporales de las 4 parcelas (para gráfica):**

```flux
from(bucket: "agro_iot_data")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "sensor_data" and r._field == "temperatura_aire")
  |> aggregateWindow(every: 1m, fn: mean, createEmpty: false)
```

---

## 6. Solución de problemas comunes

| Síntoma | Causa probable | Solución |
|---|---|---|
| `node-red: command not found` | npm global path no está en `$PATH` | Ver `npm config get prefix`, añadir `<prefix>/bin` al PATH |
| Puerto 1880 ocupado | Otro proceso usa el puerto | `node-red -p 1881` o matar el proceso anterior |
| InfluxDB no levanta | Versión 3 instalada sin querer | `brew uninstall --ignore-dependencies influxdb && brew install influxdb@2` |
| Node-RED no puede conectarse al broker MQTT | Mosquitto no corre | `brew services start mosquitto` |
| Mensaje "401 Unauthorized" del nodo InfluxDB Out | Token incorrecto o sin permisos sobre el bucket | Volver al paso 2.4 y crear un token con permisos R/W al bucket |
| Mensaje "404 not found" del nodo InfluxDB Out | Org o bucket mal escritos | Revisar exactamente `agricultura` y `agro_iot_data` (sensible a mayúsculas) |
| El bucket aparece vacío después de varios mensajes | El campo `field` se mandó como string, no número | Verificar que la función transformación use `parseFloat(p.valor)` |
| Performance pobre con 32 sensores publicando | Cada mensaje genera una conexión HTTP | Cambiar `influxdb out` por `influxdb batch` (mismo paquete) |

### 6.1 Reiniciar todo

```bash
brew services restart mosquitto
brew services restart influxdb@2
# Reiniciar Node-RED: Ctrl+C en la terminal donde corre y volver a ejecutar
```

### 6.2 Ver logs

```bash
# InfluxDB
tail -f /opt/homebrew/var/log/influxdb2/influxd.log    # Apple Silicon
tail -f /usr/local/var/log/influxdb2/influxd.log       # Intel

# Node-RED (si lo tienes con pm2)
pm2 logs node-red

# Mosquitto
tail -f /opt/homebrew/var/log/mosquitto/mosquitto.log
```

---

## 7. Detener y limpiar

```bash
# Detener servicios
brew services stop influxdb@2
brew services stop mosquitto
# Node-RED: Ctrl+C en la terminal o `pm2 stop node-red`

# Si quieres borrar TODO y empezar limpio
brew services stop influxdb@2
rm -rf ~/.influxdbv2          # Borra todos los buckets/tokens locales
brew services start influxdb@2
# Vuelves al paso 2.3 (setup inicial)
```

---

## 8. Siguientes pasos

Con InfluxDB recibiendo datos en tiempo real, el proyecto está listo para:

- **Fase 4**: procesamiento en tiempo real (limpieza, transformaciones agregadas en Node-RED).
- **Fase 5**: alertas (umbrales agronómicos sobre las series almacenadas).
- **Fase 6**: analítica/ML (Grafana lee directamente de InfluxDB con las mismas credenciales).

---

**Listo.** Pasa al notebook `Fase3_Ingesta_InfluxDB.ipynb` para ejecutar el pipeline end-to-end y capturar las evidencias.
