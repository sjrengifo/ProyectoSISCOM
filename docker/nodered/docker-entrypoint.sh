#!/bin/sh
# Entrypoint de Node-RED para Docker SISCOM
# Genera flows_cred.json con el token InfluxDB desde la variable de entorno
# antes de arrancar Node-RED, de modo que los nodos InfluxDB tengan credenciales.

set -e

echo ">>> Generando flows_cred.json con token InfluxDB..."
cat > /data/flows_cred.json << EOF
{
  "influx_server_v2_raw": { "token": "${INFLUX_TOKEN}" },
  "influx_server_v2_ind": { "token": "${INFLUX_TOKEN}" }
}
EOF

echo ">>> Iniciando Node-RED..."
exec node-red --settings /data/settings.js "$@"
