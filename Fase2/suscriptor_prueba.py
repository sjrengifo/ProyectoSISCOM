#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
 FASE 2 — Suscriptor MQTT de prueba
================================================================================

Permite verificar que el simulador está publicando correctamente.
Equivalente a `mosquitto_sub -h localhost -t "agricultura/#" -v` pero implementado
en Python para que se pueda ejecutar directamente desde IDE
y capturar evidencia (logs).

Uso:
    python suscriptor_prueba.py
    python suscriptor_prueba.py --topico "agricultura/caña/+/temperatura_aire"
    python suscriptor_prueba.py --duracion 30   # detiene tras 30 s
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import datetime

import paho.mqtt.client as mqtt

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s | %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("suscriptor")


def main():
    parser = argparse.ArgumentParser(description="Suscriptor MQTT de prueba")
    parser.add_argument("--broker",   default="localhost")
    parser.add_argument("--puerto",   type=int, default=1883)
    parser.add_argument("--topico",   default="agricultura/#",
                        help='Patrón de tópicos. Comodines: + (un nivel), # (todos).')
    parser.add_argument("--duracion", type=int, default=None,
                        help="Detener tras N segundos (default: corre indefinidamente).")
    args = parser.parse_args()

    contador = {"n": 0, "por_parcela": {}, "por_variable": {}}

    def on_connect(client, userdata, flags, rc, properties=None):
        log.info("Conectado al broker %s:%d (rc=%s)", args.broker, args.puerto, rc)
        client.subscribe(args.topico, qos=1)
        log.info("Suscrito al patrón: %s", args.topico)

    def on_message(client, userdata, msg):
        contador["n"] += 1
        try:
            data = json.loads(msg.payload.decode("utf-8"))
        except Exception:
            log.warning("[%d] %s | (no JSON) %s", contador["n"], msg.topic, msg.payload[:80])
            return

        # Acumuladores para el resumen final
        parcela = data.get("parcela", "?")
        variable = data.get("variable", "?")
        contador["por_parcela"][parcela]   = contador["por_parcela"].get(parcela, 0) + 1
        contador["por_variable"][variable] = contador["por_variable"].get(variable, 0) + 1

        # Log línea por mensaje recibido
        valor = data.get("valor", "")
        unidad = data.get("unidad", "")
        log.info("[#%05d] %-55s | %s = %s %s",
                 contador["n"], msg.topic, variable, valor, unidad)

    try:
        client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                             client_id="suscriptor_prueba_icesi")
    except (AttributeError, TypeError):
        client = mqtt.Client(client_id="suscriptor_prueba_icesi")

    client.on_connect = on_connect
    client.on_message = on_message

    log.info("Conectando a %s:%d ...", args.broker, args.puerto)
    client.connect(args.broker, args.puerto, keepalive=60)

    inicio = time.time()
    try:
        if args.duracion is not None:
            client.loop_start()
            time.sleep(args.duracion)
            client.loop_stop()
        else:
            client.loop_forever()
    except KeyboardInterrupt:
        log.info("Interrumpido por usuario.")
    finally:
        elapsed = time.time() - inicio
        log.info("=" * 60)
        log.info("RESUMEN: %d mensajes en %.1f s (%.2f msg/s)",
                 contador["n"], elapsed, contador["n"] / max(elapsed, 0.001))
        log.info("Mensajes por parcela:")
        for k, v in sorted(contador["por_parcela"].items()):
            log.info("    %-12s : %d", k, v)
        log.info("Mensajes por variable:")
        for k, v in sorted(contador["por_variable"].items(), key=lambda x: -x[1]):
            log.info("    %-22s : %d", k, v)
        client.disconnect()


if __name__ == "__main__":
    main()
