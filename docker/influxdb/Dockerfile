FROM influxdb:2.7

# Copiar el script de init y eliminar posibles \r de Windows (CRLF → LF)
# Esto evita el error "No such file or directory" en el shebang #!/bin/bash\r
COPY init/01-create-buckets.sh /docker-entrypoint-initdb.d/01-create-buckets.sh
RUN sed -i 's/\r//' /docker-entrypoint-initdb.d/01-create-buckets.sh && \
    chmod +x /docker-entrypoint-initdb.d/01-create-buckets.sh
