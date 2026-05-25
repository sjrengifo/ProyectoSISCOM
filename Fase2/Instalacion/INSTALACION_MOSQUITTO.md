# Instalación de Eclipse Mosquitto en macOS — Guía paso a paso

> Esta guía cubre la instalación del broker MQTT **Eclipse Mosquitto** en macOS y los pasos para verificar que está funcionando correctamente, antes de ejecutar el simulador de la Fase 2.

---

## 1. Prerrequisitos

* **macOS 11+** (Big Sur, Monterey, Ventura, Sonoma o Sequoia).
* **Homebrew** instalado. Si no lo tienes:

  ```bash
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  ```

* Python 3.10+ y `pip`.

---

## 2. Instalación de Mosquitto

### 2.1 Vía Homebrew (recomendado)

```bash
# Actualizar Homebrew
brew update

# Instalar Mosquitto (incluye broker, mosquitto_pub y mosquitto_sub)
brew install mosquitto
```

La instalación deja los binarios y archivos de configuración aquí:

| Recurso | Ubicación (Apple Silicon) | Ubicación (Intel) |
|---|---|---|
| Binarios | `/opt/homebrew/sbin/mosquitto`, `/opt/homebrew/bin/mosquitto_pub`, `/opt/homebrew/bin/mosquitto_sub` | `/usr/local/sbin/mosquitto`, `/usr/local/bin/mosquitto_pub`, `/usr/local/bin/mosquitto_sub` |
| Configuración | `/opt/homebrew/etc/mosquitto/mosquitto.conf` | `/usr/local/etc/mosquitto/mosquitto.conf` |
| Logs | `/opt/homebrew/var/log/mosquitto/mosquitto.log` | `/usr/local/var/log/mosquitto/mosquitto.log` |

### 2.2 Verificar la versión instalada

```bash
mosquitto -h | head -2
# mosquitto version 2.0.x
```

---

## 3. Configuración mínima

Por defecto, las versiones recientes de Mosquitto **solo aceptan conexiones desde `localhost` y rechazan clientes anónimos**. Para el laboratorio es suficiente con permitir conexiones locales anónimas.

### 3.1 Editar `mosquitto.conf`

```bash
# Apple Silicon
nano /opt/homebrew/etc/mosquitto/mosquitto.conf
# Intel
nano /usr/local/etc/mosquitto/mosquitto.conf
```

Añadir o asegurar las siguientes líneas:

```conf
# Listener en el puerto estándar 1883 (sin TLS) accesible solo en localhost
listener 1883 localhost

# Permitir clientes anónimos solo para desarrollo local
allow_anonymous true

# Persistencia opcional (recomendada)
persistence true
persistence_location /opt/homebrew/var/mosquitto/   # cambiar a /usr/local/... en Intel

# Log a archivo
log_dest file /opt/homebrew/var/log/mosquitto/mosquitto.log
log_type all
```

> **Producción:** en un despliegue real **nunca** usar `allow_anonymous true`. Configurar `password_file`, ACLs, y TLS. Para el alcance del laboratorio académico la configuración anterior es aceptable.

### 3.2 Crear los directorios de log y persistencia (si no existen)

```bash
sudo mkdir -p /opt/homebrew/var/mosquitto /opt/homebrew/var/log/mosquitto
sudo chown -R "$(whoami)" /opt/homebrew/var/mosquitto /opt/homebrew/var/log/mosquitto
```

---

## 4. Iniciar el broker

### 4.1 Como servicio de fondo (recomendado para uso diario)

```bash
brew services start mosquitto
```

Verificar:

```bash
brew services list | grep mosquitto
# mosquitto    started
```

### 4.2 En primer plano con logs verbose (recomendado para depurar)

```bash
mosquitto -c /opt/homebrew/etc/mosquitto/mosquitto.conf -v
```

Deberías ver mensajes parecidos a:

```
1714600000: mosquitto version 2.0.18 starting
1714600000: Config loaded from /opt/homebrew/etc/mosquitto/mosquitto.conf.
1714600000: Opening ipv4 listen socket on port 1883.
1714600000: Opening ipv6 listen socket on port 1883.
1714600000: mosquitto version 2.0.18 running
```

### 4.3 Detener el broker

```bash
# Si fue iniciado como servicio
brew services stop mosquitto

# Si fue iniciado en primer plano
Ctrl+C
```

---

## 5. Verificar que el broker funciona

### 5.1 Verificar que está escuchando en el puerto 1883

```bash
lsof -iTCP:1883 -sTCP:LISTEN
# COMMAND     PID USER ...    NODE NAME
# mosquitto   1234 user ...   TCP localhost:1883 (LISTEN)
```

### 5.2 Test publish/subscribe en dos terminales

**Terminal A** (suscriptor):

```bash
mosquitto_sub -h localhost -t "test/hola" -v
```

**Terminal B** (publicador):

```bash
mosquitto_pub -h localhost -t "test/hola" -m "¡Mosquitto funciona!"
```

En el Terminal A debería aparecer:

```
test/hola ¡Mosquitto funciona!
```

Si esto funciona, el broker está listo para recibir mensajes del simulador de la Fase 2.

---

## 6. Instalar la librería `paho-mqtt` para Python

```bash
# Recomendado: usar un entorno virtual
python3 -m venv .venv
source .venv/bin/activate

# Instalar dependencias
pip install paho-mqtt pandas
```

Verificar:

```bash
python3 -c "import paho.mqtt.client as mqtt; print(mqtt.__version__ if hasattr(mqtt,'__version__') else 'OK')"
```

---

## 7. Ejecutar el simulador de la Fase 2

Con Mosquitto corriendo en `localhost:1883`:

```bash
# Terminal 1: suscriptor (evidencia de recepción)
mosquitto_sub -h localhost -t "agricultura/#" -v

# Terminal 2: simulador
python simulador_sensores.py --duracion 60 --max-mensajes 50
```

Para ver únicamente las publicaciones de **caña en parcela_1**:

```bash
mosquitto_sub -h localhost -t "agricultura/caña/parcela_1/#" -v
```

Para ver únicamente las temperaturas de **todas las parcelas**:

```bash
mosquitto_sub -h localhost -t "agricultura/+/+/temperatura_aire" -v
```

---

## 8. Solución de problemas comunes (troubleshooting)

| Síntoma | Causa probable | Solución |
|---|---|---|
| `Error: Connection refused` al conectar | Mosquitto no está corriendo | `brew services start mosquitto` o ejecutarlo en primer plano |
| `Error: Unable to connect (Refused, not authorized)` | `allow_anonymous false` (defecto en >= 2.0) | Editar `mosquitto.conf` y poner `allow_anonymous true` (solo desarrollo) |
| Cliente conecta pero no llegan mensajes | Topic mal escrito o el listener escucha solo en `localhost` | Verificar que el `host` del cliente sea `localhost`, no `127.0.0.1` si hay restricciones; revisar el patrón del topic |
| `Address already in use` al iniciar | Otro proceso usa el puerto 1883 | `lsof -iTCP:1883 -sTCP:LISTEN` y matar el proceso, o cambiar de puerto |
| Conexiones que se caen rápidamente | Keepalive insuficiente | Configurar `keepalive 60` en el cliente Paho |
| Caracteres acentuados se ven mal en `mosquitto_sub` | Locale del terminal | `export LANG=es_CO.UTF-8` o `LC_ALL=en_US.UTF-8` |

### 8.1 Reiniciar Mosquitto

```bash
brew services restart mosquitto
```

### 8.2 Ver logs en vivo

```bash
tail -f /opt/homebrew/var/log/mosquitto/mosquitto.log
```

### 8.3 Reinstalar limpio

```bash
brew services stop mosquitto
brew uninstall mosquitto
brew install mosquitto
```

---

## 9. Alternativas a Mosquitto

Si el estudiante prefiere otro broker (todos compatibles MQTT 3.1.1 / 5.0):

| Broker | Cómo iniciarlo | Notas |
|---|---|---|
| **EMQX** | `brew install emqx && emqx start` | UI web en `http://localhost:18083` (admin/public) |
| **HiveMQ CE** | Descarga JAR de https://www.hivemq.com/developers/community/ | Requiere Java |
| **Aedes (Node.js)** | `npm install -g aedes-cli && aedes` | Mínimo, ideal para pruebas |
| **HiveMQ Cloud** | Free tier en https://www.hivemq.cloud/ | Broker en la nube; modificar `--broker` y credenciales en el simulador |

Para usar un broker remoto (ej. HiveMQ Cloud) basta con:

```bash
export MQTT_BROKER_HOST="xxxxx.hivemq.cloud"
export MQTT_BROKER_PORT=8883
export MQTT_USER="usuario"
export MQTT_PASS="password"
python simulador_sensores.py
```

> Si se usa un broker remoto con TLS (puerto 8883), añadir en el simulador `client.tls_set()` antes de `connect()`.

---

## 10. Lecturas complementarias

* Documentación oficial Mosquitto: https://mosquitto.org/documentation/
* Especificación MQTT 5.0 (OASIS): https://docs.oasis-open.org/mqtt/mqtt/v5.0/mqtt-v5.0.html
* Paho MQTT Python: https://eclipse.dev/paho/files/paho.mqtt.python/html/

---

**Listo.** Una vez Mosquitto esté funcionando y `paho-mqtt` instalado, el estudiante puede pasar al notebook `Fase2_Simulador_MQTT.ipynb` y ejecutar el simulador.
