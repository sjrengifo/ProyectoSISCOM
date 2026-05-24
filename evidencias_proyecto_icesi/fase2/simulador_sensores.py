#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
 FASE 2 — Simulador de sensores agrícolas IoT con MQTT
 Proyecto: Sistema de monitoreo IoT y analítica agroclimática
 Cultivos: Caña de azúcar (Valle del Cauca) y Arroz (Tolima, Casanare)
 Universidad ICESI — Sistemas y Comunicaciones I
================================================================================

Descripción
-----------
Simula una red de sensores agrícolas distribuida en 4 parcelas (2 de caña +
2 de arroz) que publican mediciones en tiempo real a un broker MQTT
(Eclipse Mosquitto). Los datos provienen del dataset agroclimático generado
en la Fase 1 (52.600 registros, 8 ubicaciones reales de Colombia).

Cada sensor publica en un tópico jerárquico de la forma:
    agricultura/<cultivo>/<parcela>/<variable>

Por ejemplo:
    agricultura/caña/parcela_1/temperatura_aire
    agricultura/arroz/parcela_3/humedad_suelo

Frecuencia de publicación: cada variable se publica con su propia cadencia
agronómicamente realista (T°/RH cada 5 s simulados, humedad de suelo cada
30 s, precipitación por evento, etc.). En la simulación estos tiempos se
acortan vía un FACTOR_ACELERACION configurable.

Uso típico
----------
    # Terminal 1: iniciar Mosquitto
    $ mosquitto -v

    # Terminal 2: suscriptor para evidencia (ver mensajes)
    $ mosquitto_sub -h localhost -t "agricultura/#" -v

    # Terminal 3: ejecutar el simulador
    $ python simulador_sensores.py

Dependencias
------------
    pip install paho-mqtt pandas
================================================================================
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import signal
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

# Cliente MQTT oficial — Eclipse Paho
import paho.mqtt.client as mqtt


# =============================================================================
#  CONFIGURACIÓN GLOBAL
# =============================================================================

# --- Conexión al broker MQTT ---
BROKER_HOST = os.environ.get("MQTT_BROKER_HOST", "localhost")
BROKER_PORT = int(os.environ.get("MQTT_BROKER_PORT", "1883"))
MQTT_USER   = os.environ.get("MQTT_USER")          # opcional, si Mosquitto pide auth
MQTT_PASS   = os.environ.get("MQTT_PASS")
KEEPALIVE   = 60                                    # segundos

# --- Topología de tópicos ---
# Convención: agricultura/<cultivo>/<parcela>/<variable>
TOPIC_BASE = "agricultura"

# --- Dataset histórico de la Fase 1 ---
DATASET_DEFAULT = "dataset_agroclimatico_colombia.csv"

# --- Definición de las 4 parcelas (alineadas con la Fase 1) ---
# Cada parcela mapea a una ubicación real del dataset.
PARCELAS = [
    {"id": "parcela_1", "cultivo": "caña",  "ubicacion": "Palmira_VAC",
     "departamento": "Valle del Cauca", "descripcion": "Caña Palmira"},
    {"id": "parcela_2", "cultivo": "caña",  "ubicacion": "Candelaria_VAC",
     "departamento": "Valle del Cauca", "descripcion": "Caña Candelaria"},
    {"id": "parcela_3", "cultivo": "arroz", "ubicacion": "Espinal_TOL",
     "departamento": "Tolima",          "descripcion": "Arroz riego (Espinal)"},
    {"id": "parcela_4", "cultivo": "arroz", "ubicacion": "Yopal_CAS",
     "departamento": "Casanare",        "descripcion": "Arroz secano (Yopal)"},
]

# --- Frecuencias agronómicamente realistas (segundos REALES en campo) ---
# Estas cadencias se basan en buenas prácticas Cenicaña/FEDEARROZ:
#   * T°/HR del aire:     cada 5 minutos
#   * Radiación solar:    cada 5 minutos
#   * Viento:             cada 10 minutos
#   * Humedad de suelo:   cada 15 minutos
#   * Precipitación:      por evento (basculación pluviómetro)
#   * pH del suelo:       1 vez por hora (suficiente, varía lento)
#   * Temperatura suelo:  cada 10 minutos
FRECUENCIAS_REALES_SEG = {
    "temperatura_aire":   300,    # 5 min
    "humedad_relativa":   300,    # 5 min
    "radiacion_solar":    300,    # 5 min
    "velocidad_viento":   600,    # 10 min
    "humedad_suelo":      900,    # 15 min
    "precipitacion":      60,     # 1 min (pulsos)
    "ph_suelo":           3600,   # 1 h
    "temperatura_suelo":  600,    # 10 min
}

# Factor de aceleración: comprime el tiempo simulado para que en pocos
# minutos veamos varias horas/días de campo. Por defecto 1 minuto real
# = 1 hora simulada (factor 60).
FACTOR_ACELERACION = float(os.environ.get("FACTOR_ACELERACION", "60"))

# --- Mapeo dataset → variables del sensor ---
# Las columnas del CSV de Fase 1 son: T2M, T2M_MAX, T2M_MIN, RH2M,
# PRECTOTCORR, ALLSKY_SFC_SW_DWN, WS2M, pH_suelo, humedad_suelo_pct.
MAPEO_DATASET = {
    "temperatura_aire":  "T2M",
    "humedad_relativa":  "RH2M",
    "precipitacion":     "PRECTOTCORR",
    "radiacion_solar":   "ALLSKY_SFC_SW_DWN",
    "velocidad_viento":  "WS2M",
    "ph_suelo":          "pH_suelo",
    "humedad_suelo":     "humedad_suelo_pct",
    # Variables derivadas (no presentes en el dataset, se sintetizan):
    #   - temperatura_suelo: estimada como T2M - 1.5 °C (referencia FAO).
}

# --- Unidades de cada variable, embebidas en el payload MQTT ---
UNIDADES = {
    "temperatura_aire":  "°C",
    "humedad_relativa":  "%",
    "precipitacion":     "mm",
    "radiacion_solar":   "MJ/m2/dia",
    "velocidad_viento":  "m/s",
    "ph_suelo":          "pH",
    "humedad_suelo":     "%",
    "temperatura_suelo": "°C",
}

# --- Logging ---
LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, datefmt="%H:%M:%S")
log = logging.getLogger("simulador")


# =============================================================================
#  CLASE SENSOR — Representa un sensor físico individual de una parcela
# =============================================================================

@dataclass
class Sensor:
    """Representa un sensor agrícola individual.

    Cada sensor monitorea UNA variable en UNA parcela y publica en el
    tópico MQTT correspondiente con la frecuencia agronómica adecuada.
    """
    parcela_id: str         # ej. "parcela_1"
    cultivo: str            # ej. "caña"
    ubicacion: str          # ej. "Palmira_VAC"
    variable: str           # clave de FRECUENCIAS_REALES_SEG
    columna_dataset: Optional[str]  # nombre de columna en el CSV (None = sintética)
    frecuencia_real_seg: int        # cadencia en segundos REALES de campo

    @property
    def topico(self) -> str:
        return f"{TOPIC_BASE}/{self.cultivo}/{self.parcela_id}/{self.variable}"

    @property
    def frecuencia_simulada(self) -> float:
        """Frecuencia ajustada por el factor de aceleración."""
        return self.frecuencia_real_seg / FACTOR_ACELERACION

    def construir_payload(self, valor: float, fecha_simulada: datetime) -> dict:
        """Construye el payload JSON estandarizado del mensaje MQTT."""
        return {
            "timestamp_real":     datetime.now(timezone.utc).isoformat(),
            "timestamp_simulado": fecha_simulada.isoformat(),
            "parcela":            self.parcela_id,
            "cultivo":            self.cultivo,
            "ubicacion":          self.ubicacion,
            "variable":           self.variable,
            "valor":              round(float(valor), 3),
            "unidad":             UNIDADES.get(self.variable, ""),
            "sensor_id":          f"{self.parcela_id}_{self.variable}",
        }


# =============================================================================
#  CLASE BROKERMQTT — Encapsula la conexión y publicación al broker
# =============================================================================

class BrokerMQTT:
    """Wrapper sobre el cliente Paho MQTT con manejo de reconexión y
    contadores de mensajes publicados."""

    def __init__(self, host: str = BROKER_HOST, port: int = BROKER_PORT,
                 client_id: str = "simulador_agro_icesi"):
        self.host = host
        self.port = port
        # API v2 (paho-mqtt >= 2.0); en versiones anteriores se usa
        # mqtt.Client(client_id=...) sin el argumento callback_api_version.
        try:
            self.client = mqtt.Client(
                callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                client_id=client_id,
            )
        except (AttributeError, TypeError):
            self.client = mqtt.Client(client_id=client_id)

        self.client.on_connect    = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_publish    = self._on_publish

        # Last Will and Testament: si el simulador muere abruptamente,
        # el broker notificará a los suscriptores.
        self.client.will_set(
            f"{TOPIC_BASE}/sistema/estado",
            payload=json.dumps({"estado": "desconectado_inesperado"}),
            qos=1, retain=True,
        )

        if MQTT_USER:
            self.client.username_pw_set(MQTT_USER, MQTT_PASS)

        self.contador_publicados = 0
        self.contador_errores    = 0
        self._lock = threading.Lock()

    # --- Callbacks Paho ---
    def _on_connect(self, client, userdata, flags, rc, properties=None):
        # rc puede ser int o ReasonCode (paho v2)
        rc_val = int(rc) if not isinstance(rc, int) else rc
        if rc_val == 0:
            log.info("Conectado al broker MQTT %s:%s ✓", self.host, self.port)
            # Anunciar que el simulador está activo
            client.publish(
                f"{TOPIC_BASE}/sistema/estado",
                payload=json.dumps({"estado": "activo",
                                    "timestamp": datetime.now(timezone.utc).isoformat()}),
                qos=1, retain=True,
            )
        else:
            log.error("Falló conexión MQTT, código=%s", rc_val)

    def _on_disconnect(self, client, userdata, *args):
        log.warning("Desconectado del broker MQTT")

    def _on_publish(self, client, userdata, mid, *args):
        with self._lock:
            self.contador_publicados += 1

    # --- API pública ---
    def conectar(self) -> None:
        log.info("Conectando a %s:%s ...", self.host, self.port)
        self.client.connect(self.host, self.port, keepalive=KEEPALIVE)
        self.client.loop_start()  # hilo en background para callbacks/keepalive
        time.sleep(0.5)           # dar tiempo al callback on_connect

    def publicar(self, topico: str, payload: dict, qos: int = 1) -> bool:
        """Publica un payload JSON. Devuelve True si fue aceptado."""
        msg = json.dumps(payload, ensure_ascii=False)
        info = self.client.publish(topico, payload=msg, qos=qos, retain=False)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            with self._lock:
                self.contador_errores += 1
            return False
        return True

    def desconectar(self) -> None:
        # Mensaje de baja limpia
        self.client.publish(
            f"{TOPIC_BASE}/sistema/estado",
            payload=json.dumps({"estado": "apagado_limpio",
                                "timestamp": datetime.now(timezone.utc).isoformat()}),
            qos=1, retain=True,
        )
        time.sleep(0.3)
        self.client.loop_stop()
        self.client.disconnect()
        log.info("Desconectado del broker. Total publicados: %d | errores: %d",
                 self.contador_publicados, self.contador_errores)


# =============================================================================
#  DATASET — Carga del CSV histórico de Fase 1
# =============================================================================

def cargar_dataset(ruta: str) -> pd.DataFrame:
    """Carga el dataset agroclimático y normaliza tipos."""
    if not Path(ruta).exists():
        log.error("No se encontró el dataset en %s", ruta)
        log.error("Asegúrate de tener el archivo de la Fase 1 en el directorio.")
        sys.exit(1)
    df = pd.read_csv(ruta, parse_dates=["fecha"])
    log.info("Dataset cargado: %d registros, %d columnas", len(df), len(df.columns))
    return df


def filtrar_por_parcela(df: pd.DataFrame, ubicacion: str) -> pd.DataFrame:
    """Filtra el dataset por la ubicación correspondiente a la parcela."""
    sub = df[df["ubicacion"] == ubicacion].sort_values("fecha").reset_index(drop=True)
    if sub.empty:
        log.warning("Sin registros para ubicación %s", ubicacion)
    else:
        log.info("  • %s: %d registros (%s a %s)",
                 ubicacion, len(sub),
                 sub["fecha"].iloc[0].date(), sub["fecha"].iloc[-1].date())
    return sub


# =============================================================================
#  HILO DE SENSOR — Bucle de publicación independiente por sensor
# =============================================================================

def hilo_sensor(sensor: Sensor,
                df_parcela: pd.DataFrame,
                broker: BrokerMQTT,
                evento_parar: threading.Event,
                logger_evidencia: Optional["LoggerEvidencia"] = None,
                max_mensajes: Optional[int] = None) -> None:
    """Bucle principal de un sensor. Recorre el dataset fila por fila
    publicando con la cadencia simulada correspondiente."""
    if df_parcela.empty:
        log.error("[%s] Sin datos, hilo terminado.", sensor.topico)
        return

    cadencia = sensor.frecuencia_simulada
    n_filas = len(df_parcela)
    contador = 0
    idx = 0

    log.info("[%s] iniciado | cadencia=%.2fs | n=%d filas",
             sensor.topico, cadencia, n_filas)

    while not evento_parar.is_set():
        fila = df_parcela.iloc[idx % n_filas]
        # Obtener valor: si la variable está mapeada al dataset, usar columna;
        # si no, sintetizar (ej. temperatura_suelo).
        if sensor.columna_dataset and sensor.columna_dataset in fila.index:
            valor_base = fila[sensor.columna_dataset]
        elif sensor.variable == "temperatura_suelo":
            # Aproximación: temp del suelo ≈ T_aire - 1.5 °C (Allen et al., FAO-56)
            valor_base = float(fila.get("T2M", 25.0)) - 1.5
        else:
            valor_base = 0.0

        # Manejar NaN (datos faltantes que no fueron imputados)
        if pd.isna(valor_base):
            log.debug("[%s] valor NaN, se omite publicación", sensor.topico)
            idx += 1
            evento_parar.wait(cadencia)
            continue

        # Añadir un pequeño ruido de medición realista (±1 % a ±3 %)
        valor = float(valor_base) * (1.0 + random.gauss(0, 0.015))

        # Construir y publicar
        fecha_sim = pd.Timestamp(fila["fecha"]).to_pydatetime()
        payload = sensor.construir_payload(valor, fecha_sim)
        ok = broker.publicar(sensor.topico, payload, qos=1)

        if ok:
            contador += 1
            if logger_evidencia is not None:
                logger_evidencia.registrar(sensor.topico, payload)
            if contador % 10 == 0:
                log.info("[%s] %d mensajes publicados (último valor=%.2f %s)",
                         sensor.topico, contador, payload["valor"], payload["unidad"])
        else:
            log.warning("[%s] error publicando", sensor.topico)

        if max_mensajes is not None and contador >= max_mensajes:
            log.info("[%s] alcanzado límite de %d mensajes, hilo termina.",
                     sensor.topico, max_mensajes)
            return

        idx += 1
        evento_parar.wait(cadencia)


# =============================================================================
#  LOGGER DE EVIDENCIA — Guarda todos los mensajes publicados a JSONL
# =============================================================================

class LoggerEvidencia:
    """Guarda en un archivo JSONL cada mensaje publicado, para que el
    estudiante tenga evidencia auditable (alternativa a screenshot)."""

    def __init__(self, ruta: str = "evidencia_publicaciones.jsonl"):
        self.ruta = ruta
        self._lock = threading.Lock()
        # Limpiar archivo al inicio
        Path(self.ruta).write_text("", encoding="utf-8")
        log.info("Evidencia se registrará en %s", self.ruta)

    def registrar(self, topico: str, payload: dict) -> None:
        registro = {"topico": topico, **payload}
        linea = json.dumps(registro, ensure_ascii=False)
        with self._lock, open(self.ruta, "a", encoding="utf-8") as f:
            f.write(linea + "\n")


# =============================================================================
#  CONSTRUCCIÓN DEL CONJUNTO DE SENSORES
# =============================================================================

def construir_sensores(parcelas: list[dict]) -> list[Sensor]:
    """Genera el listado de sensores: cada parcela tiene un sensor por
    cada variable agroclimática relevante (8 sensores × 4 parcelas = 32).
    Algunas variables no aplican igual a todos los cultivos (ej. en arroz
    riego la humedad de suelo es lámina, en caña es tensión), pero se
    publican igual y se diferenciarán por cultivo en el tópico."""
    sensores: list[Sensor] = []
    for p in parcelas:
        for variable, freq in FRECUENCIAS_REALES_SEG.items():
            sensores.append(Sensor(
                parcela_id          = p["id"],
                cultivo             = p["cultivo"],
                ubicacion           = p["ubicacion"],
                variable            = variable,
                columna_dataset     = MAPEO_DATASET.get(variable),
                frecuencia_real_seg = freq,
            ))
    return sensores


# =============================================================================
#  ORQUESTACIÓN — Lanzamiento del simulador completo
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Simulador IoT de sensores agrícolas (Fase 2)")
    parser.add_argument("--dataset", default=DATASET_DEFAULT,
                        help="Ruta al CSV de Fase 1.")
    parser.add_argument("--broker", default=BROKER_HOST,
                        help="Host del broker MQTT (default: localhost).")
    parser.add_argument("--puerto", type=int, default=BROKER_PORT,
                        help="Puerto MQTT (default: 1883).")
    parser.add_argument("--max-mensajes", type=int, default=None,
                        help="Detener cada hilo tras N mensajes (útil para evidencia).")
    parser.add_argument("--duracion", type=int, default=None,
                        help="Detener todo el simulador tras N segundos.")
    parser.add_argument("--evidencia", default="evidencia_publicaciones.jsonl",
                        help="Archivo JSONL con todos los mensajes publicados.")
    args = parser.parse_args()

    # Cargar dataset
    df = cargar_dataset(args.dataset)

    # Construir sensores
    sensores = construir_sensores(PARCELAS)
    log.info("Total parcelas: %d | Total sensores instanciados: %d",
             len(PARCELAS), len(sensores))
    for p in PARCELAS:
        log.info("  → %s (%s, %s) — %s",
                 p["id"], p["cultivo"], p["ubicacion"], p["descripcion"])

    # Conectar broker
    broker = BrokerMQTT(host=args.broker, port=args.puerto)
    broker.conectar()

    # Logger de evidencia
    evidencia = LoggerEvidencia(args.evidencia)

    # Lanzar un hilo por sensor
    evento_parar = threading.Event()
    hilos: list[threading.Thread] = []

    # Pre-filtrar el dataset por ubicación (eficiencia)
    cache_parcela: dict[str, pd.DataFrame] = {}
    for p in PARCELAS:
        cache_parcela[p["ubicacion"]] = filtrar_por_parcela(df, p["ubicacion"])

    for s in sensores:
        df_p = cache_parcela[s.ubicacion]
        t = threading.Thread(
            target=hilo_sensor,
            args=(s, df_p, broker, evento_parar, evidencia, args.max_mensajes),
            name=f"sensor_{s.parcela_id}_{s.variable}",
            daemon=True,
        )
        t.start()
        hilos.append(t)

    # Manejo de Ctrl+C
    def manejar_senal(signum, frame):
        log.info("Señal %d recibida, deteniendo el simulador...", signum)
        evento_parar.set()
    signal.signal(signal.SIGINT,  manejar_senal)
    signal.signal(signal.SIGTERM, manejar_senal)

    log.info("Simulador en ejecución. Presiona Ctrl+C para detener.")

    try:
        if args.duracion is not None:
            evento_parar.wait(args.duracion)
            evento_parar.set()
        # Esperar que todos los hilos terminen (cuando max-mensajes se alcanza
        # o cuando Ctrl+C activa el evento).
        for t in hilos:
            t.join()
    finally:
        broker.desconectar()
        log.info("Simulador detenido. Mensajes en evidencia: %s",
                 sum(1 for _ in open(args.evidencia, encoding="utf-8")))


if __name__ == "__main__":
    main()
