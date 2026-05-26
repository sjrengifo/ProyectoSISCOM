# SISCOM — Sistema Integral de Seguimiento de Cultivos

**Universidad ICESI — Sistemas y Comunicaciones I**

Proyecto: Plataforma IoT para monitoreo agroclimatico de parcelas de cana de azucar y arroz en Colombia.

---

## Estructura del repositorio

| Carpeta | Descripcion | Notebook | Evidencia |
|---------|-------------|---------|-----------|
| `Fase0/` | Investigacion, requisitos y marco teorico IoT | `Fase0_IoT_Agricultura_Digital.docx` | — |
| `Fase1/` | Exploracion del dataset (52 600 registros, 2007–2024, NASA POWER) | `Fase1_Exploracion_Dataset.ipynb` | `Fase1/` |
| `Fase2/` | Simulador MQTT: 32 sensores virtuales, 4 parcelas | `Fase2_Simulador_MQTT.ipynb` | `Fase2/Evidencia/` |
| `Fase3/` | Ingestion MQTT → InfluxDB via Node-RED | `Fase3_Ingesta_InfluxDB.ipynb` | `Fase3/Evidencia/` |
| `Fase4/` | Pipeline de procesamiento: limpieza + 5 indicadores agronomicos | `Fase4_Procesamiento_Pipeline.ipynb` | `Fase4/Evidencia/` |
| `Fase5/` | Servicio de alertas: 24 umbrales, Email / SMS / WhatsApp | `Fase5_Alertas.ipynb` | `Fase5/Evidencia/` |
| `Fase6/` | Analitica predictiva: Random Forest + Gradient Boosting | `Fase6_Analitica_Prediccion.ipynb` | `Fase6/Run/` |
| `Fase7/` | Dashboards Grafana (4 paneles interactivos) | `Fase7_Dashboard.ipynb` | `Fase7/Evidencia/` |
| `docker/` | Entorno reproducible Docker (Windows / macOS / Linux) | — | — |

**Notebook consolidado presentado en clase 25/05/26**: `Proyecto_Consolidado.ipynb` — recorre las 7 fases con todos los outputs de la sustentacion, este notebook es el que evidencia detalladamente como se cumplen los requerimientos de la rubrica.

**Presentación de clase 25/05/26**: `Mosquera_Rengifo_SISCOM_IoT.pdf`

---

## Inicio rapido con Docker (Windows / macOS / Linux)

### Requisitos previos

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) >= 4.x instalado y en ejecucion
- Git

> **Windows**: abrir **PowerShell** o **Git Bash** para los comandos siguientes.

### Levantar la infraestructura (3 comandos)

```bash
git clone https://github.com/sjrengifo/ProyectoSISCOM.git
cd ProyectoSISCOM/docker
docker compose up -d
```

Docker construye las imagenes la primera vez (~3–5 min) y luego inicia:

| Servicio | URL | Credenciales |
|---------|-----|-------------|
| Grafana (dashboards) | http://localhost:3000 | `admin` / `siscom2026` |
| InfluxDB (base de datos) | http://localhost:8086 | `admin` / `siscom2026` |
| Node-RED (flujos) | http://localhost:1880 | sin autenticacion |

Los dashboards de Grafana se cargan automaticamente desde `Fase7/` en la carpeta **Agro-ICESI**.

---

### Poblar datos historicos (ultimos 7 dias)

Ejecuta una sola vez para ver los dashboards con datos reales:

```bash
docker compose --profile poblar run --rm poblar
```

Esto inserta 8 dias de datos calculados (variables climaticas + 5 indicadores agronomicos) en InfluxDB.

---

### Simulador en tiempo real

Genera datos continuos simulando sensores IoT desde el dataset historico:

```bash
docker compose --profile simulador up simulador
```

- Publica mensajes MQTT al broker Mosquitto
- Node-RED los consume, calcula indicadores y los escribe en InfluxDB
- Los dashboards de Grafana se actualizan en tiempo real

Detener el simulador: `Ctrl+C`

---

### Servicio de alertas

Evalua umbrales agronomicos cada minuto y envia notificaciones por correo cuando se superan los 24 umbrales definidos en `Fase5/umbrales_agronomicos.yaml`.

#### Configurar Gmail para recibir alertas

El servicio usa SMTP con Gmail. Si la cuenta tiene **verificacion en 2 pasos activada** (MFA), no puede usarse la contrasena normal — Gmail la rechaza. Se necesita una **Contrasena de Aplicacion**:

1. Ir a [myaccount.google.com](https://myaccount.google.com) con el correo que quieres usar
2. `Seguridad` → `Verificacion en 2 pasos` → activar si aun no esta activa
3. En el buscador de configuracion de la cuenta escribir **"contrasenas de aplicacion"**
4. Seleccionar app: **Correo** / dispositivo: **Otro (nombre personalizado)** → `SISCOM`
5. Google genera una clave de 16 caracteres (ej: `abcd efgh ijkl mnop`) — **copiarla sin espacios**
6. Editar `docker/.env` con esas credenciales:

```env
SMTP_USER=tu_correo@gmail.com
SMTP_PASSWORD=abcdefghijklmnop    # Contrasena de Aplicacion (16 chars, sin espacios)
```

> Si prefieres usar una cuenta Gmail nueva sin MFA, basta con activar
> "Acceso de aplicaciones menos seguras" en la configuracion de la cuenta
> y usar la contrasena normal. Esta opcion la tiene desactivada Google por
> defecto desde 2022, pero se puede reactivar en cuentas sin 2FA.

#### Levantar el servicio

```bash
docker compose --profile alertas up -d alertas
```

Ver logs en tiempo real:
```bash
docker compose logs -f alertas
```

#### Inyectar una alerta de prueba

El servicio evalua umbrales sobre los **indicadores calculados por Node-RED**. Si los datos actuales no superan ningun umbral, no se genera ninguna alerta real — esto es el comportamiento correcto del sistema. Para verificar que el canal de notificaciones funciona sin esperar a que los datos lo activen, usa el siguiente comando:

```bash
docker compose run --rm alertas python /app/docker/python/test_notificacion.py
```

Esto envia un correo HTML simulando una alerta CRITICA de temperatura a la cuenta configurada en `SMTP_USER`. El correo incluye parcela, variable, valor medido, umbral superado y accion sugerida — identico al formato de una alerta real.

> Para enviar la prueba a un correo diferente del remitente, agrega la variable
> `SMTP_DEST=otro@correo.com` en `docker/.env`.

---

### JupyterLab (explorar notebooks)

```bash
docker compose --profile jupyter up jupyter
```

Abrir en el navegador: **http://localhost:8888** (sin contrasena)

Desde JupyterLab se puede abrir cualquier notebook de las carpetas `Fase1/` a `Fase7/` y explorar el codigo con acceso completo al proyecto.

---

## Parametros configurables

Editar el archivo `docker/.env` antes de ejecutar `docker compose up`:

| Variable | Valor por defecto | Descripcion |
|---------|-------------------|-------------|
| `SIMULADOR_DURACION` | `3600` | Duracion del simulador en segundos (0 = sin limite) |
| `FACTOR_ACELERACION` | `60` | Velocidad de simulacion (60 = 1 dia real en 1 minuto) |
| `INFLUX_TOKEN` | `siscom-agro-2026-...` | Token de autenticacion InfluxDB |
| `GRAFANA_ADMIN_PASSWORD` | `siscom2026` | Contrasena del admin de Grafana |
| `SMTP_USER` | `administradorparcelasiscom@gmail.com` | Correo para alertas |
| `SMTP_PASSWORD` | `4dminSiscom2026` | Contrasena del correo de alertas |
| `TWILIO_ACCOUNT_SID` | `ACeeb0a7...` | SID de cuenta Twilio para SMS/WhatsApp |
| `TWILIO_AUTH_TOKEN` | `3a3bfa3...` | Token de autenticacion Twilio |

---

## Modelo de Machine Learning

### Opcion A — Usar el modelo pre-entrenado (predeterminado)

El archivo `Fase6/modelos_agroclimaticos_fase6.joblib` ya esta incluido en el repositorio.
El simulador y el poblador de datos lo cargan automaticamente. No se requiere ninguna accion adicional.

El modelo incluye:
- **Clasificadores**: Random Forest y Gradient Boosting para riesgo hidrico
- **Regresores**: prediccion de temperatura minima, maxima, humedad y radiacion solar
- **Preprocesamiento**: StandardScaler con features de lag (t-1, t-2, t-3, rolling 7 dias)

### Opcion B — Entrenar el modelo desde cero

1. Levantar JupyterLab:
   ```bash
   docker compose --profile jupyter up jupyter
   ```
2. Abrir en el navegador: http://localhost:8888
3. Navegar a `Fase6/Fase6_Analitica_Prediccion.ipynb`
4. Ejecutar todas las celdas (aprox. 5 min en un equipo moderno)
5. El nuevo modelo sobreescribe `Fase6/modelos_agroclimaticos_fase6.joblib`

---

## Detener y limpiar

```bash
# Detener servicios (conserva los datos en volúmenes)
docker compose down

# Detener y eliminar todos los datos (reset total)
docker compose down -v
```

---

## Arquitectura del sistema

```
Dataset CSV (NASA POWER)
        |
        v
Fase2: Simulador MQTT  ──── publica ────►  Mosquitto (broker)
                                                  |
                                                  v
                                        Fase3/4: Node-RED
                                        (ingestion + pipeline)
                                                  |
                                    ┌─────────────┴────────────┐
                                    v                          v
                             InfluxDB: agro_iot_data   InfluxDB: agro_iot_indicadores
                             (datos raw)               (5 indicadores agronomicos)
                                    |                          |
                          ┌─────────┴──────────┐              |
                          v                    v              v
                   Fase7: Grafana       Fase5: Alertas   Fase6: ML
                   (4 dashboards)       (Email/SMS/WA)   (prediccion)
```

**5 indicadores agronomicos calculados en Node-RED:**
1. Indice de Estres Hidrico (IEH)
2. Indice de Calor Acumulado (GDD)
3. Eficiencia Hidrica (EH)
4. Presion de Vapor Deficit (VPD)
5. Indice de Condicion del Cultivo (ICC)

---

## Ejecucion manual (macOS / Linux con Homebrew)

Si prefieres ejecutar los servicios de forma nativa sin Docker:

```bash
# Instalar dependencias
brew install mosquitto influxdb node-red grafana
brew services start mosquitto
brew services start influxdb

# Entorno Python
cd ProyectoSISCOM
python -m venv venv && source venv/bin/activate
pip install paho-mqtt influxdb-client pandas numpy scikit-learn joblib scipy matplotlib seaborn PyYAML requests twilio jupyterlab

# Iniciar Node-RED
node-red &

# Simulador
python Fase2/simulador_sensores.py --dataset Fase2/dataset_agroclimatico_colombia.csv --broker localhost

# Servicio de alertas
python Fase5/servicio_alertas.py --config Fase5/umbrales_agronomicos.yaml

# Poblar datos historicos
python Fase7/poblar_dia_completo.py --fecha $(date +%Y-%m-%d)
```
