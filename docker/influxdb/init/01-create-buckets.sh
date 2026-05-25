#!/bin/bash
# InfluxDB init script — crea el segundo bucket agro_iot_indicadores
# (InfluxDB ya crea agro_iot_data automáticamente via DOCKER_INFLUXDB_INIT_BUCKET)
#
# NOTA: durante el init, influxd corre en INFLUXD_INIT_PORT (9999 por defecto),
# no en 8086. No se debe especificar --host para que la CLI use su config file.

INIT_HOST="http://localhost:${INFLUXD_INIT_PORT:-9999}"

echo ">>> Creando bucket ${DOCKER_INFLUXDB_INIT_BUCKET_IND}..."
influx bucket create \
  --name "${DOCKER_INFLUXDB_INIT_BUCKET_IND}" \
  --org "${DOCKER_INFLUXDB_INIT_ORG}" \
  --retention 365d \
  --token "${DOCKER_INFLUXDB_INIT_ADMIN_TOKEN}" \
  --host "${INIT_HOST}" 2>/dev/null || echo ">>> Bucket ya existe, continuando."

echo ">>> Buckets disponibles:"
influx bucket list \
  --org "${DOCKER_INFLUXDB_INIT_ORG}" \
  --token "${DOCKER_INFLUXDB_INIT_ADMIN_TOKEN}" \
  --host "${INIT_HOST}"
