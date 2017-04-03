# Dockerfile used to run the prox-scheduler backend service

FROM python:3-alpine
MAINTAINER Chris Blake <chris@servernetworktech.com>

LABEL Description="This image is used to run the prox-scheduler backend"

# Create our own account to run under once ready
ENV RUN_USER            backend
ENV RUN_GROUP           backend

# Add build packages and user
RUN \
  apk add --no-cache bash zlib build-base g++ zlib-dev mariadb-dev \
  mariadb-client mariadb-libs mariadb-client-libs cyrus-sasl-dev \
  openssh-client tar openssl-dev libffi-dev \
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

# Generate ourself an SSH key to use when building/downloading
RUN \
  mkdir ~/.ssh \
  && ssh-keygen -b 4096 -t rsa -f ~/.ssh/id_rsa -q -N ""

# Set the default working directory as our homedir
WORKDIR /home/${RUN_USER}

# Define our DL volume
VOLUME ["/builds"]

# Run our backend launcher
CMD ["./launcher.sh"]
