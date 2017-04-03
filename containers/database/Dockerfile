# Dockerfile used to run the prox-scheduler database (MariaDB)

FROM mariadb:latest
MAINTAINER Chris Blake <chris@servernetworktech.com>

LABEL Description="This image is used to run the prox-scheduler MariaDB Database"

# Copy over our .sql file that we run at start if we are a new container
COPY ./src/prox-scheduler.sql /docker-entrypoint-initdb.d/prox-scheduler.sql
