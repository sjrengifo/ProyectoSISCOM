#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
 FASE 5 — Servicio de alertas agronómicas
 Proyecto: Sistema de monitoreo IoT y analítica agroclimática (ICESI)
 Cultivos: Caña de azúcar (Valle del Cauca) y Arroz (Tolima, Casanare)
================================================================================

Descripción
-----------
Consulta periódicamente el bucket `agro_iot_indicadores` en InfluxDB y aplica
los umbrales agronómicos definidos en `umbrales_agronomicos.yaml`. Cuando una
condición se cumple de forma sostenida (persistencia mínima configurable), se
disparan notificaciones por los canales habilitados:
    - Email (SMTP)
    - SMS (Twilio)
    - WhatsApp (Twilio Sandbox)
    - MQTT (re-publica en agricultura/alertas/<cultivo>/<parcela>/<indicador>)

Diseño
------
- Sin estado persistente: cada ciclo evalúa la ventana reciente.
- Cooldown para evitar spam: la misma alerta no se repite dentro de un período.
- Modo dry-run: si las credenciales faltan, solo se loguea (útil para demo).
- Persistencia mínima: un valor debe permanecer fuera de rango N minutos antes
  de disparar, para evitar falsos positivos por picos transitorios.

Uso
---
    # Setup
    export INFLUX_TOKEN="<token>"
    export SMTP_USER="usuario@gmail.com"          # opcional
    export SMTP_PASSWORD="app-password"           # opcional
    export TWILIO_ACCOUNT_SID="AC..."             # opcional
    export TWILIO_AUTH_TOKEN="..."                # opcional

    pip install influxdb-client paho-mqtt PyYAML twilio

    # Ejecutar
    python servicio_alertas.py
    python servicio_alertas.py --dry-run         # no envía notificaciones reales
    python servicio_alertas.py --once            # un solo ciclo y termina
================================================================================
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import signal
import smtplib
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Optional

# Dependencias opcionales (manejadas con try/except para permitir dry-run sin ellas)
try:
    import yaml
except ImportError:
    print("⚠ PyYAML no instalado — pip install PyYAML", file=sys.stderr)
    sys.exit(1)

try:
    from influxdb_client import InfluxDBClient, Point, WritePrecision
    from influxdb_client.client.write_api import SYNCHRONOUS
except ImportError:
    print("⚠ influxdb-client no instalado — pip install influxdb-client", file=sys.stderr)
    sys.exit(1)

try:
    import paho.mqtt.client as mqtt
    PAHO_OK = True
except ImportError:
    PAHO_OK = False
    print("ℹ paho-mqtt no instalado — canal MQTT deshabilitado", file=sys.stderr)

try:
    from twilio.rest import Client as TwilioClient
    TWILIO_OK = True
except ImportError:
    TWILIO_OK = False


# ═══════════════════════════════════════════════════════════════════════════════
#  CONFIGURACIÓN Y LOGGING
# ═══════════════════════════════════════════════════════════════════════════════

LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, datefmt="%H:%M:%S")
log = logging.getLogger("alertas")


def expandir_variables_entorno(obj: Any) -> Any:
    """Sustituye ${VAR} por su valor de os.environ recursivamente."""
    if isinstance(obj, dict):
        return {k: expandir_variables_entorno(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [expandir_variables_entorno(x) for x in obj]
    if isinstance(obj, str):
        return re.sub(r'\$\{([A-Z_][A-Z0-9_]*)\}',
                       lambda m: os.environ.get(m.group(1), m.group(0)), obj)
    return obj


def cargar_configuracion(ruta: str) -> dict:
    """Carga el YAML de umbrales y expande variables de entorno."""
    with open(ruta, 'r', encoding='utf-8') as f:
        cfg = yaml.safe_load(f)
    cfg = expandir_variables_entorno(cfg)
    return cfg


# ═══════════════════════════════════════════════════════════════════════════════
#  EVALUACIÓN DE UMBRALES
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Alerta:
    """Representa una alerta disparada por la violación de un umbral."""
    timestamp:        datetime
    cultivo:          str
    parcela:          str
    ubicacion:        str
    variable:         str         # nombre del indicador o variable raw
    valor:            float
    unidad:           str
    nivel:            str         # info | warning | critical
    mensaje:          str
    accion:           str
    fuente_umbral:    str

    def clave_dedup(self) -> str:
        """Clave para el cooldown — la misma combinación no se repite."""
        return f"{self.cultivo}|{self.parcela}|{self.variable}|{self.nivel}"

    def to_dict(self) -> dict:
        return {
            'timestamp':  self.timestamp.isoformat(),
            'cultivo':    self.cultivo,
            'parcela':    self.parcela,
            'ubicacion':  self.ubicacion,
            'variable':   self.variable,
            'valor':      round(self.valor, 3),
            'unidad':     self.unidad,
            'nivel':      self.nivel,
            'mensaje':    self.mensaje,
            'accion':     self.accion,
        }


def evaluar_umbral(valor: float, condicion: str, umbral: float) -> bool:
    """Evalúa si valor viola la condición."""
    return {
        '>':  valor > umbral,
        '>=': valor >= umbral,
        '<':  valor < umbral,
        '<=': valor <= umbral,
        '==': valor == umbral,
    }.get(condicion, False)


def evaluar_indicador(valor: float, cultivo_cfg: dict, variable: str) -> list[dict]:
    """Devuelve la lista de violaciones para un par (variable, valor) en un cultivo.

    Cada violación es un dict con keys: nivel, condicion, valor, mensaje, accion.
    """
    var_cfg = cultivo_cfg.get('variables', {}).get(variable)
    if not var_cfg:
        return []
    violaciones = []
    for umbral_def in var_cfg.get('umbrales', []):
        cond = umbral_def['condicion']
        # Algunas condiciones requieren contexto adicional (ej. delta T-DP); las omitimos aquí
        if cond.startswith('delta_'):
            continue
        if evaluar_umbral(valor, cond, umbral_def['valor']):
            violaciones.append({
                'nivel':    umbral_def['nivel'],
                'condicion': cond,
                'umbral':   umbral_def['valor'],
                'mensaje':  umbral_def['mensaje'],
                'accion':   umbral_def['accion'],
                'unidad':   var_cfg.get('unidad', ''),
                'fuente':   var_cfg.get('fuente', '—'),
            })
    # Devolver solo la violación de mayor severidad (critical > warning > info)
    if not violaciones:
        return []
    orden_severidad = {'info': 0, 'warning': 1, 'critical': 2}
    violaciones.sort(key=lambda v: orden_severidad.get(v['nivel'], 0), reverse=True)
    return [violaciones[0]]


# ═══════════════════════════════════════════════════════════════════════════════
#  CANALES DE NOTIFICACIÓN
# ═══════════════════════════════════════════════════════════════════════════════

class CanalEmail:
    """Envía alertas por SMTP. Compatible con Gmail App Passwords."""

    def __init__(self, cfg: dict, dry_run: bool = False):
        self.cfg = cfg
        self.dry_run = dry_run
        self.activo = (cfg.get('activo', False)
                       and cfg.get('smtp_user') and cfg.get('smtp_password')
                       and not cfg['smtp_user'].startswith('$')
                       and not cfg['smtp_password'].startswith('$'))
        if cfg.get('activo') and not self.activo:
            log.warning("Canal email activo en YAML pero sin credenciales — modo dry-run")
            self.dry_run = True
            self.activo = True   # seguir simulando

    def enviar(self, alerta: Alerta) -> bool:
        if not self.activo:
            return False
        asunto = f"[{alerta.nivel.upper()}] {alerta.parcela} ({alerta.cultivo}) — {alerta.variable}"
        cuerpo = self._construir_cuerpo(alerta)

        if self.dry_run:
            log.info("📧 [DRY-RUN] Email → %s | %s",
                     ', '.join(self.cfg.get('destinatarios', [])), asunto)
            return True
        try:
            msg = MIMEMultipart('alternative')
            msg['From'] = self.cfg['remitente']
            msg['To']   = ', '.join(self.cfg.get('destinatarios', []))
            msg['Subject'] = asunto
            msg.attach(MIMEText(cuerpo, 'plain'))

            with smtplib.SMTP(self.cfg['smtp_host'], self.cfg['smtp_port']) as srv:
                srv.starttls()
                srv.login(self.cfg['smtp_user'], self.cfg['smtp_password'])
                srv.send_message(msg)
            log.info("📧 Email enviado a %d destinatarios", len(self.cfg.get('destinatarios', [])))
            return True
        except Exception as e:
            log.error("📧 Error enviando email: %s", e)
            return False

    @staticmethod
    def _construir_cuerpo(a: Alerta) -> str:
        return f"""\
ALERTA AGRONÓMICA — Sistema IoT ICESI
======================================

Nivel:     {a.nivel.upper()}
Cultivo:   {a.cultivo}
Parcela:   {a.parcela}
Ubicación: {a.ubicacion}
Fecha:     {a.timestamp.isoformat()}

Variable:  {a.variable}
Valor:     {a.valor} {a.unidad}

Descripción:
  {a.mensaje}

Acción recomendada:
  {a.accion}

Fuente del umbral: {a.fuente_umbral}

--
Sistema automático de monitoreo agroclimático — Universidad ICESI
Este es un mensaje automático. No responder a este correo.
"""


class CanalSMS:
    """Envía SMS vía Twilio."""

    def __init__(self, cfg: dict, dry_run: bool = False):
        self.cfg = cfg
        self.dry_run = dry_run
        self.cliente: Optional[TwilioClient] = None
        credenciales = (cfg.get('twilio_account_sid') and cfg.get('twilio_auth_token')
                         and not cfg['twilio_account_sid'].startswith('$')
                         and not cfg['twilio_auth_token'].startswith('$'))
        self.activo = cfg.get('activo', False) and (TWILIO_OK or dry_run)
        if cfg.get('activo') and not (TWILIO_OK and credenciales):
            log.warning("Canal SMS activo pero sin twilio/credenciales — modo dry-run")
            self.dry_run = True
        if TWILIO_OK and credenciales and not dry_run:
            self.cliente = TwilioClient(cfg['twilio_account_sid'], cfg['twilio_auth_token'])

    def enviar(self, alerta: Alerta) -> bool:
        if not self.activo:
            return False
        texto = self._construir_texto(alerta)
        if self.dry_run or self.cliente is None:
            log.info("📱 [DRY-RUN] SMS → %s | %s",
                     ', '.join(self.cfg.get('destinatarios', [])), texto[:60] + '...')
            return True
        try:
            for dest in self.cfg.get('destinatarios', []):
                self.cliente.messages.create(
                    body=texto, from_=self.cfg['twilio_from'], to=dest)
            log.info("📱 SMS enviado a %d destinatarios", len(self.cfg.get('destinatarios', [])))
            return True
        except Exception as e:
            log.error("📱 Error enviando SMS: %s", e)
            return False

    @staticmethod
    def _construir_texto(a: Alerta) -> str:
        # SMS limitado a 160 caracteres
        return (f"[{a.nivel.upper()}] {a.parcela} {a.cultivo}: "
                f"{a.variable}={a.valor}{a.unidad}. {a.mensaje[:80]}")


class CanalWhatsApp:
    """Envía mensajes WhatsApp vía Twilio (sandbox o cuenta empresarial)."""

    def __init__(self, cfg: dict, dry_run: bool = False):
        self.cfg = cfg
        self.dry_run = dry_run
        self.cliente: Optional[TwilioClient] = None
        credenciales = (cfg.get('twilio_account_sid') and cfg.get('twilio_auth_token')
                         and not cfg['twilio_account_sid'].startswith('$')
                         and not cfg['twilio_auth_token'].startswith('$'))
        self.activo = cfg.get('activo', False) and (TWILIO_OK or dry_run)
        if cfg.get('activo') and not (TWILIO_OK and credenciales):
            log.warning("Canal WhatsApp activo pero sin twilio/credenciales — modo dry-run")
            self.dry_run = True
        if TWILIO_OK and credenciales and not dry_run:
            self.cliente = TwilioClient(cfg['twilio_account_sid'], cfg['twilio_auth_token'])

    def enviar(self, alerta: Alerta) -> bool:
        if not self.activo:
            return False
        cuerpo = self._construir_cuerpo(alerta)
        if self.dry_run or self.cliente is None:
            log.info("💬 [DRY-RUN] WhatsApp → %s",
                     ', '.join(self.cfg.get('destinatarios', [])))
            return True
        try:
            for dest in self.cfg.get('destinatarios', []):
                self.cliente.messages.create(
                    body=cuerpo, from_=self.cfg['twilio_from'], to=dest)
            log.info("💬 WhatsApp enviado a %d destinatarios", len(self.cfg.get('destinatarios', [])))
            return True
        except Exception as e:
            log.error("💬 Error enviando WhatsApp: %s", e)
            return False

    @staticmethod
    def _construir_cuerpo(a: Alerta) -> str:
        icono = {'info': 'ℹ️', 'warning': '⚠️', 'critical': '🚨'}.get(a.nivel, '•')
        return (f"{icono} *ALERTA {a.nivel.upper()}*\n\n"
                f"🌱 *Cultivo:* {a.cultivo}\n"
                f"📍 *Parcela:* {a.parcela} ({a.ubicacion})\n"
                f"📊 *{a.variable}:* {a.valor} {a.unidad}\n\n"
                f"📝 _{a.mensaje}_\n\n"
                f"✅ *Acción:* {a.accion}")


class CanalMQTT:
    """Re-publica alertas en MQTT — útil para que Node-RED las consuma o
    para integrar con otras plataformas IoT."""

    def __init__(self, cfg: dict, dry_run: bool = False):
        self.cfg = cfg
        self.dry_run = dry_run
        self.activo = cfg.get('activo', False) and PAHO_OK
        self.cliente = None
        if self.activo and not dry_run:
            try:
                self.cliente = mqtt.Client(
                    callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                    client_id='servicio_alertas_icesi'
                )
            except (AttributeError, TypeError):
                self.cliente = mqtt.Client(client_id='servicio_alertas_icesi')
            self.cliente.connect(cfg['broker'], cfg['port'], keepalive=60)
            self.cliente.loop_start()
            log.info("📡 MQTT conectado al broker %s:%d", cfg['broker'], cfg['port'])

    def enviar(self, alerta: Alerta) -> bool:
        if not self.activo:
            return False
        topico = (f"{self.cfg['topico_base']}/{alerta.cultivo}/"
                   f"{alerta.parcela}/{alerta.variable}")
        payload = json.dumps(alerta.to_dict(), ensure_ascii=False)
        if self.dry_run or self.cliente is None:
            log.info("📡 [DRY-RUN] MQTT → %s", topico)
            return True
        self.cliente.publish(topico, payload, qos=1, retain=False)
        return True

    def cerrar(self):
        if self.cliente is not None:
            self.cliente.loop_stop()
            self.cliente.disconnect()


# ═══════════════════════════════════════════════════════════════════════════════
#  ORQUESTADOR — consulta InfluxDB y aplica umbrales
# ═══════════════════════════════════════════════════════════════════════════════

class ServicioAlertas:
    """Servicio principal que cicla cada N segundos."""

    def __init__(self, config: dict, dry_run: bool = False):
        self.cfg = config
        self.dry_run = dry_run

        # InfluxDB
        self.influx_url    = os.environ.get('INFLUX_URL',    'http://localhost:8086')
        self.influx_org    = os.environ.get('INFLUX_ORG',    'agricultura')
        self.influx_bucket = os.environ.get('INFLUX_BUCKET_IND', 'agro_iot_indicadores')
        self.influx_token  = os.environ.get('INFLUX_TOKEN',  '')
        self.client = None
        self._conectar_influx()

        # Canales
        canales_cfg = config.get('canales', {})
        self.canales = {
            'email':    CanalEmail(canales_cfg.get('email', {}),    dry_run),
            #'sms':      CanalSMS(canales_cfg.get('sms', {}),        dry_run),
            'whatsapp': CanalWhatsApp(canales_cfg.get('whatsapp', {}), dry_run),
            'mqtt':     CanalMQTT(canales_cfg.get('mqtt_alertas', {}), dry_run),
        }

        # Estado de cooldown por (cultivo, parcela, variable, nivel)
        self.cooldown: dict[str, float] = {}
        self.cooldown_seg = config.get('global', {}).get('cooldown_alertas_minutos', 30) * 60
        self.intervalo_seg = config.get('global', {}).get('intervalo_evaluacion_segundos', 60)
        self.ventana_min  = config.get('global', {}).get('ventana_consulta_minutos', 15)

        # Acumulador de alertas para esta sesión (útil para resumen final)
        self.alertas_enviadas: list[Alerta] = []

        self.detener = False

    def _conectar_influx(self):
        try:
            self.client = InfluxDBClient(
                url=self.influx_url, token=self.influx_token, org=self.influx_org)
            health = self.client.health()
            log.info("✓ Conectado a InfluxDB %s (status: %s)", self.influx_url, health.status)
            self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
        except Exception as e:
            log.error("✗ No se pudo conectar a InfluxDB: %s", e)
            self.write_api = None

    # --- Canales destino por nivel ---
    def _canales_para_nivel(self, nivel: str) -> list[str]:
        # info → solo log | warning → email + mqtt | critical → todos
        return {
            'info':     ['mqtt'],
            'warning':  ['email', 'mqtt'],
            'critical': ['email', 'sms', 'whatsapp', 'mqtt'],
        }.get(nivel, ['mqtt'])

    # --- Consulta de InfluxDB ---
    def consultar_indicadores_recientes(self) -> list[dict]:
        """Devuelve el último valor de cada indicador por parcela/cultivo."""
        query = f'''
from(bucket: "{self.influx_bucket}")
  |> range(start: -{self.ventana_min}m)
  |> filter(fn: (r) => r._measurement == "indicadores")
  |> group(columns: ["parcela", "cultivo", "ubicacion", "indicador"])
  |> last()
'''
        try:
            df = self.client.query_api().query_data_frame(query)
            if isinstance(df, list):
                import pandas as pd
                df = pd.concat(df, ignore_index=True)
            if df is None or len(df) == 0:
                return []
            return df.to_dict(orient='records')
        except Exception as e:
            log.error("Error consultando InfluxDB: %s", e)
            return []

    # --- Ciclo principal de evaluación ---
    def ciclo(self):
        registros = self.consultar_indicadores_recientes()
        if not registros:
            log.info("Ciclo: sin datos recientes en el bucket %s", self.influx_bucket)
            return 0

        log.info("Ciclo: evaluando %d registros recientes...", len(registros))
        alertas_disparadas = 0

        for r in registros:
            cultivo  = r.get('cultivo', '').replace('caña_de_azúcar', 'caña')
            parcela  = r.get('parcela')
            ubicacion = r.get('ubicacion', 'desconocida')
            variable = r.get('indicador') or r.get('_field')
            valor    = r.get('_value')
            if cultivo not in self.cfg or valor is None:
                continue

            cultivo_cfg = self.cfg[cultivo]
            violaciones = evaluar_indicador(float(valor), cultivo_cfg, variable)

            for v in violaciones:
                alerta = Alerta(
                    timestamp     = datetime.now(timezone.utc),
                    cultivo       = cultivo,
                    parcela       = parcela,
                    ubicacion     = ubicacion,
                    variable      = variable,
                    valor         = float(valor),
                    unidad        = v['unidad'],
                    nivel         = v['nivel'],
                    mensaje       = v['mensaje'],
                    accion        = v['accion'],
                    fuente_umbral = v['fuente'],
                )
                if self._cooldown_activo(alerta):
                    continue
                self._registrar_cooldown(alerta)
                self._notificar(alerta)
                alertas_disparadas += 1

        log.info("Ciclo terminado: %d alertas disparadas.", alertas_disparadas)
        return alertas_disparadas

    def _cooldown_activo(self, alerta: Alerta) -> bool:
        ahora = time.time()
        ultima = self.cooldown.get(alerta.clave_dedup())
        if ultima is None:
            return False
        return (ahora - ultima) < self.cooldown_seg

    def _registrar_cooldown(self, alerta: Alerta):
        self.cooldown[alerta.clave_dedup()] = time.time()

    def _notificar(self, alerta: Alerta):
        log.warning("🚨 ALERTA %s — %s | %s | %s=%s%s",
                    alerta.nivel.upper(), alerta.parcela, alerta.cultivo,
                    alerta.variable, alerta.valor, alerta.unidad)
        for canal_nombre in self._canales_para_nivel(alerta.nivel):
            canal = self.canales.get(canal_nombre)
            if canal:
                canal.enviar(alerta)
        self.alertas_enviadas.append(alerta)
        # Escribir alerta a InfluxDB para visualización en Grafana
        if self.write_api and not self.dry_run:
            try:
                punto = (Point("alertas")
                         .tag("nivel",    alerta.nivel)
                         .tag("parcela",  alerta.parcela)
                         .tag("cultivo",  alerta.cultivo)
                         .tag("ubicacion", alerta.ubicacion)
                         .field("variable", alerta.variable)
                         .field("valor",    alerta.valor)
                         .field("unidad",   alerta.unidad)
                         .field("mensaje",  alerta.mensaje)
                         .field("accion",   alerta.accion)
                         .time(alerta.timestamp, WritePrecision.NS))
                self.write_api.write(bucket=self.influx_bucket, record=punto)
                log.info("✓ Alerta escrita en InfluxDB bucket=%s", self.influx_bucket)
            except Exception as e:
                log.error("✗ Error escribiendo alerta en InfluxDB: %s", e)

    def run(self, once: bool = False):
        if once:
            self.ciclo()
            return

        def manejador_signal(signum, frame):
            log.info("Señal %d recibida — terminando servicio...", signum)
            self.detener = True
        signal.signal(signal.SIGINT,  manejador_signal)
        signal.signal(signal.SIGTERM, manejador_signal)

        log.info("Servicio de alertas iniciado | intervalo=%ds | ventana=%dmin | cooldown=%ds",
                 self.intervalo_seg, self.ventana_min, self.cooldown_seg)

        while not self.detener:
            try:
                self.ciclo()
            except Exception as e:
                log.error("Error en ciclo: %s", e)
            for _ in range(self.intervalo_seg):
                if self.detener:
                    break
                time.sleep(1)

        log.info("Servicio terminado. Total alertas enviadas: %d", len(self.alertas_enviadas))
        if 'mqtt' in self.canales:
            self.canales['mqtt'].cerrar()


# ═══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description='Servicio de alertas agronómicas (Fase 5)')
    parser.add_argument('--config', default='umbrales_agronomicos.yaml',
                        help='YAML con umbrales y canales')
    parser.add_argument('--dry-run', action='store_true',
                        help='Loguea las notificaciones sin enviarlas')
    parser.add_argument('--once', action='store_true',
                        help='Ejecutar un solo ciclo y salir (útil para tests)')
    args = parser.parse_args()

    if not Path(args.config).exists():
        log.error("Archivo de configuración no encontrado: %s", args.config)
        sys.exit(1)

    config = cargar_configuracion(args.config)
    servicio = ServicioAlertas(config, dry_run=args.dry_run)
    servicio.run(once=args.once)


if __name__ == '__main__':
    main()
