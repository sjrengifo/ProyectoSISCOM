FROM nodered/node-red:3.1.9

# Instalar plugin InfluxDB 2.x compatible
RUN npm install node-red-contrib-influxdb@0.7.0

# Copiar configuración pre-adaptada para Docker
COPY flow_fase4_docker.json /data/flows.json
COPY settings.js             /data/settings.js
COPY --chmod=755 docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
