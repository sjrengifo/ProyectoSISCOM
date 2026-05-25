# Configuración de la Fase 5 — Servicio de alertas agronómicas

Esta guía explica paso a paso cómo configurar los **cuatro canales de notificación** del servicio de alertas (`servicio_alertas.py`) en macOS. El servicio NO requiere instalaciones nuevas de infraestructura; reutiliza los servicios que ya tienes desde las Fases 2-4 (Mosquitto, InfluxDB, Node-RED).

> **Prerequisito:** las Fases 3 y 4 deben estar operativas. El bucket `agro_iot_indicadores` (creado en Fase 4) debe estar recibiendo datos del flow Node-RED de procesamiento.

---

## 1. Instalación de dependencias Python

```bash
# Cliente InfluxDB v2 + utilidades
pip install influxdb-client pandas

# Cliente MQTT (re-publicación a agricultura/alertas/...)
pip install paho-mqtt

# Parser YAML (umbrales declarativos)
pip install PyYAML

# Twilio (SMS y WhatsApp) — opcional, sin esto el servicio sigue funcionando
# en dry-run para esos canales
pip install twilio
```

Verifica que todo está disponible:

```bash
python3 -c "import influxdb_client, paho.mqtt.client, yaml, twilio; print('✓ Todas las dependencias')"
```

---

## 2. Variables de entorno requeridas

Crea un archivo `.env` o exporta directamente (recomendado `direnv` o `.envrc` para no commitear):

```bash
# === InfluxDB v2 (de la Fase 3) ===
export INFLUX_URL="http://localhost:8086"
export INFLUX_ORG="agricultura"
export INFLUX_BUCKET_IND="agro_iot_indicadores"
export INFLUX_TOKEN="tu_token_aqui"

# === Email (Gmail App Password) ===
export SMTP_USER="alertas-agro-icesi@gmail.com"
export SMTP_PASSWORD="abcd efgh ijkl mnop"   # 16 chars, espacios opcionales

# === Twilio (SMS + WhatsApp) ===
export TWILIO_ACCOUNT_SID="ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
export TWILIO_AUTH_TOKEN="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

> El servicio sustituye automáticamente cada `${VARIABLE}` que aparece en `umbrales_agronomicos.yaml` por el valor de la variable de entorno. Si una variable falta, el canal correspondiente cae a **dry-run** (loguea pero no envía).

---

## 3. Configuración de Email (Gmail App Password)

Gmail bloquea autenticación SMTP con contraseña normal desde 2022. Hay que generar una **App Password** (16 caracteres).

### 3.1 Activar verificación en 2 pasos

1. Ir a [https://myaccount.google.com/security](https://myaccount.google.com/security)
2. **Verificación en 2 pasos** → activar (requiere un teléfono).

### 3.2 Generar App Password

1. Buscar [https://myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) (solo accesible con 2FA activado).
2. **Nombre de la app**: `alertas-agro-icesi`.
3. **Generar** → se muestra una clave tipo `abcd efgh ijkl mnop`.
4. **Copiar inmediatamente** (no se vuelve a mostrar) y exportar:

```bash
export SMTP_USER="alertas-agro-icesi@gmail.com"
export SMTP_PASSWORD="abcdefghijklmnop"   # los espacios pueden omitirse
```

### 3.3 Probar la conexión

```bash
python3 -c "
import smtplib
from email.mime.text import MIMEText
import os

msg = MIMEText('Test de alerta — Fase 5')
msg['Subject'] = '[TEST] Servicio de alertas funcionando'
msg['From']    = os.environ['SMTP_USER']
msg['To']      = os.environ['SMTP_USER']

with smtplib.SMTP('smtp.gmail.com', 587) as srv:
    srv.starttls()
    srv.login(os.environ['SMTP_USER'], os.environ['SMTP_PASSWORD'])
    srv.send_message(msg)
print('✓ Email de prueba enviado')
"
```

---

## 4. Configuración de SMS (Twilio)

Twilio cobra ~$0.05 USD por SMS internacional pero ofrece **$15 USD gratis** al registrarse (≈300 SMS de prueba).

### 4.1 Crear cuenta Twilio

1. Ir a [https://www.twilio.com/try-twilio](https://www.twilio.com/try-twilio).
2. Registrarse (verifica con un número de teléfono real).
3. Después del onboarding aparece el **Console** con:
   - **Account SID** (empieza con `AC...`).
   - **Auth Token** (clic en "show").
4. Exportar:

```bash
export TWILIO_ACCOUNT_SID="ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
export TWILIO_AUTH_TOKEN="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

### 4.2 Obtener un número remitente Twilio

1. En el Console: **Phone Numbers → Manage → Buy a number**.
2. País: **United States** (el más barato — ~$1/mes para trial).
3. Capability: marcar **SMS**.
4. Comprar → el número aparece en formato `+12025550100`.
5. Editar `umbrales_agronomicos.yaml` y reemplazar `twilio_from` en la sección `sms` con tu número:

```yaml
sms:
  activo: true
  proveedor: twilio
  twilio_account_sid: ${TWILIO_ACCOUNT_SID}
  twilio_auth_token:  ${TWILIO_AUTH_TOKEN}
  twilio_from:        "+12025550100"   # ← tu número Twilio
  destinatarios:
    - "+57XXXXXXXXXX"   # ← tu móvil colombiano (con +57)
```

### 4.3 Verificar números destinatarios (cuentas trial)

En modo trial, Twilio solo envía SMS a **números verificados**:

1. **Phone Numbers → Manage → Verified Caller IDs → Add a new Caller ID**.
2. Ingresar el móvil de cada destinatario (con código de país +57).
3. Recibirás un código por SMS — ingresar para verificar.

> Cuando pases a una cuenta de pago (upgrade), puedes enviar a cualquier número.

### 4.4 Probar el envío SMS

```bash
python3 -c "
from twilio.rest import Client
import os
c = Client(os.environ['TWILIO_ACCOUNT_SID'], os.environ['TWILIO_AUTH_TOKEN'])
msg = c.messages.create(
    body='Test alerta agronómica — Fase 5 ICESI',
    from_='+12025550100',           # ← cámbialo a tu número Twilio
    to='+57XXXXXXXXXX'              # ← cámbialo a tu móvil verificado
)
print(f'✓ SMS enviado: SID={msg.sid}')
"
```

---

## 5. Configuración de WhatsApp (Twilio Sandbox)

Twilio ofrece un **Sandbox de WhatsApp** gratuito que no requiere aprobación de Meta — perfecto para esta fase académica.

### 5.1 Activar el Sandbox

1. En el Console Twilio: **Messaging → Try it out → Send a WhatsApp message**.
2. Verás un número Twilio Sandbox (típicamente `+1 415 523 8886`) y una **frase clave** tipo `join brown-fence`.
3. Desde **cada móvil que quieras usar como destinatario**:
   - Abre WhatsApp.
   - Manda un mensaje al número Twilio Sandbox: `join brown-fence` (tu frase clave).
   - Twilio responde "Connected to sandbox" — ya estás suscrito.

### 5.2 Editar el YAML

```yaml
whatsapp:
  activo: true
  proveedor: twilio
  twilio_account_sid: ${TWILIO_ACCOUNT_SID}
  twilio_auth_token:  ${TWILIO_AUTH_TOKEN}
  twilio_from:        "whatsapp:+14155238886"   # número Sandbox Twilio (NO cambiar)
  destinatarios:
    - "whatsapp:+57XXXXXXXXXX"   # tu móvil con prefijo "whatsapp:"
```

### 5.3 Probar el envío WhatsApp

```bash
python3 -c "
from twilio.rest import Client
import os
c = Client(os.environ['TWILIO_ACCOUNT_SID'], os.environ['TWILIO_AUTH_TOKEN'])
msg = c.messages.create(
    body='🚨 Test alerta agronómica — Fase 5 ICESI',
    from_='whatsapp:+14155238886',
    to='whatsapp:+57XXXXXXXXXX'   # ← tu móvil registrado en el Sandbox
)
print(f'✓ WhatsApp enviado: SID={msg.sid}')
"
```

> **Limitaciones del Sandbox**:
>   - Solo destinatarios que se hayan unido con la frase clave reciben mensajes.
>   - La sesión expira después de 72 h sin actividad — hay que volver a enviar `join <frase>`.
>   - Mensajes salientes deben ser respuesta a un mensaje del usuario en las últimas 24 h, EXCEPTO si se usan **plantillas pre-aprobadas** (el Sandbox tiene 3 de ejemplo).
>   - Para producción real: pasar a WhatsApp Business API (requiere aprobación de Meta).

---

## 6. Configuración del canal MQTT (re-publicación)

Este canal **siempre está activo** mientras Mosquitto esté corriendo. No requiere configuración extra; ya lo tienes desde la Fase 2.

Las alertas se publican en:

```
agricultura/alertas/<cultivo>/<parcela>/<variable>
```

Para suscribirte y ver las alertas en vivo desde una terminal:

```bash
mosquitto_sub -h localhost -t "agricultura/alertas/#" -v
```

O en Node-RED: añadir un nodo **MQTT In** con tópico `agricultura/alertas/#` y conectarlo a un nodo Debug.

---

## 7. Lanzar el servicio

### 7.1 Modo dry-run (no envía nada real)

Útil para validar antes de gastar SMS o spamear correos:

```bash
python3 servicio_alertas.py --dry-run --once
```

Output esperado: lista de alertas detectadas con la etiqueta `[DRY-RUN]` antes de cada envío simulado.

### 7.2 Modo producción (un solo ciclo)

```bash
python3 servicio_alertas.py --once
```

### 7.3 Modo producción (loop continuo)

```bash
python3 servicio_alertas.py
```

El servicio ciclará cada 60 segundos. `Ctrl+C` lo detiene limpiamente.

### 7.4 Como servicio persistente con pm2

Igual que hicimos con Node-RED en Fase 3:

```bash
npm install -g pm2
pm2 start servicio_alertas.py --interpreter python3 --name alertas-agro
pm2 save
pm2 startup   # sigue las instrucciones para auto-arranque
pm2 logs alertas-agro   # ver logs
```

---

## 8. Verificación end-to-end

Para forzar una alerta y confirmar que llega por todos los canales:

1. **Inyectar un valor crítico en InfluxDB**:
   ```bash
   influx write -b agro_iot_indicadores -o agricultura \
     'indicadores,parcela=parcela_4,cultivo=arroz,ubicacion=Yopal_CAS,indicador=temperatura_aire_min temperatura_aire_min=17.0'
   ```

2. **Lanzar un ciclo del servicio**:
   ```bash
   python3 servicio_alertas.py --once
   ```

3. **Esperar las 4 notificaciones** (en ~5-10 segundos):
   - 📧 Email en `agronomo_jefe@finca.co`
   - 📱 SMS en tu móvil verificado
   - 💬 WhatsApp en tu móvil registrado en Sandbox
   - 📡 Mensaje MQTT en `agricultura/alertas/arroz/parcela_4/temperatura_aire_min`

---

## 9. Solución de problemas

| Síntoma | Causa | Solución |
|---|---|---|
| `SMTPAuthenticationError` | Contraseña normal en vez de App Password | Generar App Password (sección 3.2) |
| `Authenticate` error de Twilio | SID/Token mal copiados | Copiar de nuevo del Console |
| SMS sale "queued" pero no llega | Cuenta trial + número no verificado | Verificar el destinatario (sección 4.3) |
| WhatsApp sale OK pero móvil no lo recibe | No se hizo `join <frase>` desde el móvil | Repetir paso 5.1 desde el móvil destinatario |
| `Connection refused` al MQTT | Mosquitto no corre | `brew services start mosquitto` |
| Query a InfluxDB devuelve 0 filas | El flow Node-RED de Fase 4 no escribe en `agro_iot_indicadores` | Verificar token con permisos R/W sobre AMBOS buckets |
| Las alertas se repiten cada minuto | Cooldown desactivado o muy bajo | Verificar `cooldown_alertas_minutos` en YAML (default 30 min) |

---

## 10. Costos estimados (operación real)

| Canal | Costo unitario | Volumen típico/mes | Costo mensual |
|---|---|---|---|
| Email | $0 | 200-500 alertas | $0 |
| SMS Twilio | ~$0.05 USD | 50-100 alertas críticas | $2.50-5 USD |
| WhatsApp Sandbox | $0 | sin límite | $0 |
| WhatsApp Business | ~$0.005-0.05 USD | depende del país | $0.50-5 USD |
| MQTT local | $0 | ilimitado | $0 |

Para una operación real de 4 parcelas, esperar **<$10 USD/mes** en SMS críticos.

---

## 11. Próxima fase

**Fase 6 — Analítica y aprendizaje automático:** las alertas históricas almacenadas en MQTT (`agricultura/alertas/#`) y los indicadores de InfluxDB serán los datos de entrenamiento para modelos predictivos (anticipar alertas con 6 h de adelanto, calibrar umbrales por etapa fenológica, etc.).
