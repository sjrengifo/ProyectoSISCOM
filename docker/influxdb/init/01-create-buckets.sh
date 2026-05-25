#!/bin/bash
# InfluxDB init script — crea el segundo bucket agro_iot_indicadores
# (InfluxDB ya crea agro_iot_data automáticamente via DOCKER_INFLUXDB_INIT_BUCKET)
set -e

echo ">>> Creando bucket ${DOCKER_INFLUXDB_INIT_BUCKET_IND}..."
influx bucket create \
  --name "${DOCKER_INFLUXDB_INIT_BUCKET_IND}" \
  --org "${DOCKER_INFLUXDB_INIT_ORG}" \
  --retention 365d \
  --token "${DOCKER_INFLUXDB_INIT_ADMIN_TOKEN}" \
  --host http://localhost:8086 2>/dev/null || echo ">>> Bucket ya existe, continuando."

echo ">>> Buckets disponibles:"
influx bucket list \
  --org "${DOCKER_INFLUXDB_INIT_ORG}" \
  --token "${DOCKER_INFLUXDB_INIT_ADMIN_TOKEN}" \
  --host http://localhost:8086
