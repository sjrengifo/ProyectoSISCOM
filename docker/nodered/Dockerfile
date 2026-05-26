FROM nodered/node-red:3.1.9

# Cambiar a root para instalar paquetes y manipular archivos del sistema
USER root

# Instalar plugin InfluxDB 2.x compatible
RUN npm install node-red-contrib-influxdb@0.7.0

# Copiar configuración pre-adaptada para Docker
COPY flow_fase4_docker.json /data/flows.json
COPY settings.js             /data/settings.js
COPY docker-entrypoint.sh    /usr/local/bin/docker-entrypoint.sh

# Eliminar \r de Windows (CRLF → LF) y dar permisos de ejecución
RUN sed -i 's/\r//' /usr/local/bin/docker-entrypoint.sh && \
    chmod +x /usr/local/bin/docker-entrypoint.sh

# Volver al usuario node-red (requerido por la imagen base)
USER node-red

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
