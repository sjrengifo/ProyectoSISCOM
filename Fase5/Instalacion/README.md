# FASE 5 — Definición de umbrales agronómicos y generación de alertas

Sistema completo de alertas agronómicas que consulta periódicamente los indicadores de la Fase 4 en InfluxDB, evalúa 24 umbrales fundamentados en literatura científica (Cenicaña, FEDEARROZ, FAO-56), y dispara notificaciones por **Email, SMS, WhatsApp y MQTT** según la severidad de la condición detectada.

---

## Archivos entregados

| Archivo | Propósito |
|---|---|
| `Fase5_Alertas.ipynb` | Notebook Jupyter con los 3 entregables del PDF (variables, umbrales, alertas). 18 celdas con outputs incrustados. |
| `servicio_alertas.py` | Servicio Python autónomo: ~600 líneas, 5 clases (orquestador + 4 canales), modo dry-run, cooldown anti-spam. |
| `umbrales_agronomicos.yaml` | Configuración declarativa: 24 umbrales con citas científicas, rangos óptimos y acciones recomendadas. |
| `CONFIGURACION_FASE5.md` | Guía paso a paso de Gmail App Password, Twilio (SMS+WhatsApp Sandbox), variables de entorno y troubleshooting. |
| `diagrama_arquitectura_fase5.png` | Diagrama de la arquitectura del sistema con los 4 canales de notificación. |
| `evidencia_dashboard_alertas.png` | Mockup del centro de alertas con KPIs y tabla de las 7 alertas ejemplo. |
| `evidencia_notificaciones.png` | Mockup de las notificaciones reales (email + SMS iPhone + WhatsApp lado a lado). |
| `README.md` | Este archivo. |

---

## Inicio rápido (3 pasos)

### Paso 1 — Instalar dependencias

```bash
pip install influxdb-client paho-mqtt PyYAML twilio pandas
```

### Paso 2 — Exportar credenciales

```bash
export INFLUX_TOKEN="<tu_token_de_Fase_3_4>"
export SMTP_USER="alertas-agro-icesi@gmail.com"
export SMTP_PASSWORD="<gmail_app_password>"          # 16 chars
export TWILIO_ACCOUNT_SID="AC..."
export TWILIO_AUTH_TOKEN="..."
```

> Guía completa de obtención de credenciales en `CONFIGURACION_FASE5.md`.

### Paso 3 — Lanzar

```bash
# Test sin enviar (un solo ciclo, modo dry-run)
python3 servicio_alertas.py --once --dry-run

# Producción (loop continuo cada 60 s)
python3 servicio_alertas.py
```

---

## Cumplimiento de los entregables del PDF

| # | Entregable | Cumplido | Evidencia |
|---|---|---|---|
| 1 | **Descripción de variables y rango operativo** | ✅ | Notebook §2 (12 variables × 2 cultivos con fuentes citadas) |
| 2 | **Definición de umbrales y efecto en el cultivo** | ✅ | Notebook §3 (24 umbrales con acción recomendada y fundamento agronómico) |
| 3 | **Alertas por Email, SMS, WhatsApp** | ✅ | Notebook §4-5 + `servicio_alertas.py` con las 4 clases funcionales |

---

## Resumen del sistema

### Política de canales por severidad

| Nivel | Email | SMS | WhatsApp | MQTT | Caso de uso |
|---|---|---|---|---|---|
| **INFO** | — | — | — | ✓ | Solo registro local |
| **WARNING** | ✓ | — | — | ✓ | Anomalía notable, vigilar |
| **CRITICAL** | ✓ | ✓ | ✓ | ✓ | Intervención agronómica obligatoria |

### 24 umbrales fundamentados

**Caña de azúcar (11 umbrales sobre 6 variables):**
- VPD: warning >1.6 kPa, critical >2.0 kPa *(Allen et al. FAO-56)*
- Temperatura: warning >35°C, critical >38°C, warning <20°C *(Muhammad e Imitas 2016)*
- HR sostenida >90% *(Cenicaña — roya naranja)*
- Índice de calor: warning >35°C, critical >40°C *(seguridad laboral)*
- Precipitación: warning >30 mm/día, critical >50 mm/día *(manejo drenajes)*
- ETo Hargreaves: warning >6 mm/día *(programación de riego)*

**Arroz (13 umbrales sobre 8 variables):**
- Temperatura diurna: warning >33°C, critical >35°C *(AgriCien 2020)*
- **Temperatura mínima: CRITICAL <18°C** ⚠️ *(FAO 2004 — esterilidad masiva en floración)*
- T° nocturna warning >24°C *(aborto de óvulos)*
- VPD: warning >1.6 kPa, critical >2.0 kPa
- HR >90% (Pyricularia) *(Universidad Nacional 2025)*
- Punto de rocío: T_aire − DP < 2°C (condensación)
- Precipitación: warning >40 mm, critical >80 mm *(tumbado)*
- Radiación baja <10 MJ/m²/día *(FAO — esterilidad por falta de carbohidratos)*
- ETo: warning >6 mm/día

### Características técnicas del servicio

- **Lenguaje:** Python 3.10+, ~600 líneas comentadas en español
- **Configuración:** declarativa en YAML (cambios sin tocar código)
- **Canales:** 4 clases independientes (`CanalEmail`, `CanalSMS`, `CanalWhatsApp`, `CanalMQTT`)
- **Anti-spam:** cooldown 30 min por (cultivo, parcela, variable, nivel)
- **Persistencia mínima:** una alerta solo se dispara si la condición se sostiene ≥10 min
- **Degradación elegante:** si Twilio no está instalado o las credenciales faltan, el canal cae a dry-run
- **CLI:** soporta `--once`, `--dry-run`, `--config`
- **Señales:** SIGINT/SIGTERM para shutdown limpio (útil con pm2/systemd)

---

## Validación end-to-end (modo demo)

El notebook ejecuta el servicio en modo `--once --dry-run` con datos sintéticos que **fuerzan violaciones de umbrales**. Se generan:

- **3 alertas CRITICAL** (parcela_4 arroz T°mín 17.2°C, parcela_3 arroz VPD 2.15 kPa, parcela_2 caña T° 39.1°C)
- **4 alertas WARNING** (VPD/HI/ETo Palmira + radiación Espinal)

Total enviado en un solo ciclo:
- 📧 14 emails (3 critical × 2 dest + 4 warning × 2 dest)
- 📱 6 SMS (3 critical × 2 dest)
- 💬 3 WhatsApp (3 critical × 1 dest)
- 📡 7 mensajes MQTT (todos)

---

## Frecuencia esperada de alertas con datos reales

Aplicando los umbrales sobre 18 años de datos históricos de Fase 1 (52.600 filas), las alertas son **manejables** (no saturan al agrónomo):

- Alertas CRITICAL por temperatura arroz >35°C: **<0.5% de los días** → consistente con la climatología tropical colombiana
- Alertas WARNING por VPD caña >1.6 kPa: **3-8% de los días** en temporada seca → exactamente las semanas donde el agrónomo debe intervenir
- Alertas por lluvia torrencial >50 mm/día: **pico estacional** abril-mayo y octubre-noviembre → coincide con segunda temporada bimodal

---

## Por qué este diseño es robusto

1. **No invade el flujo principal:** el servicio es un proceso **independiente** que solo lee InfluxDB. Si falla, la ingesta y el procesamiento siguen funcionando.
2. **Configuración como código:** todos los umbrales y destinatarios viven en el YAML. Un agrónomo no-programador puede ajustar umbrales editando un archivo de texto.
3. **Auditabilidad:** cada alerta lleva consigo la fuente del umbral (Cenicaña, FAO-56, etc.) para que el destinatario sepa por qué se le notifica.
4. **Acción recomendada explícita:** no basta con avisar "VPD alto" — la alerta dice "Riego inmediato. Riesgo de pérdida TCH si persiste >2 h". El agrónomo no necesita interpretar el dato.
5. **Coherencia con fases anteriores:** consume directamente lo que la Fase 4 produce, sin transformaciones adicionales. La Fase 6 (ML) recibirá un historial limpio de alertas etiquetadas.

---

## Próxima fase

**Fase 6 — Analítica y aprendizaje automático:** los datos históricos almacenados en InfluxDB + los logs de alertas serán los insumos para entrenar modelos que:

1. **Anticipen** alertas con horas de adelanto (¿puedo predecir un VPD crítico mañana para programar riego hoy?).
2. **Calibren umbrales dinámicos** según etapa fenológica (T°mín <18°C solo importa en floración).
3. **Reduzcan falsos positivos** detectando patrones de co-ocurrencia con variables externas (ENSO, fase lunar, etc.).
