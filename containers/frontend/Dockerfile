# Dockerfile used to run the prox-scheduler frontend service

FROM python:3-alpine
MAINTAINER Chris Blake <chris@servernetworktech.com>

LABEL Description="This image is used to run the prox-scheduler FLASK frontend"

# Create our own account to run under once ready
ENV RUN_USER            frontend
ENV RUN_GROUP           frontend

# Add build packages and user
RUN \
  apk add --no-cache bash zlib build-base g++ zlib-dev mariadb-dev \
  mariadb-client mariadb-libs mariadb-client-libs cyrus-sasl-dev \
  && adduser -D -u 1000 ${RUN_USER}

# Copy over requires file
ADD ./src/requires.txt /home/${RUN_USER}/

# Install our required python3 modules
RUN \
  pip3 install -r /home/${RUN_USER}/requires.txt

# Cleanup image
RUN \
  apk del build-base \
  && rm -rf /usr/src/python ~/.cache /tmp/* /var/tmp/* /var/cache/apk/*

# Copy over our source code to be ran
ADD ./src /home/${RUN_USER}

# Use our custom user for security purposes
USER ${RUN_USER}:${RUN_GROUP}

# Set the default working directory as our homedir
WORKDIR /home/${RUN_USER}

# Define our DL volume
VOLUME ["/builds"]

# Run our site
CMD ["./launcher.sh"]
