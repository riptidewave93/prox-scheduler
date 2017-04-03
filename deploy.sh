#!/bin/bash

# Are we dev?
if [ "$1" = "dev" ]; then
  cfile="compose.env.dev"
  echo "Skipping git, in dev mode."
else
  cfile="compose.env.prod"
  git pull
fi

# Do we have our config file?
if [ ! -f "./${cfile}" ]; then
  echo "Error, ${cfile} not found! Did you configure your options, and are you in the right dir?"
  exit 1
fi

# Copy our new env to what we need it to be
cp ./${cfile} ./.env

# Decom the current env
docker-compose down -v

# Generate MySQL User and Pass for our soon-to-be env
PROXSCH_DB_USER=`head /dev/urandom | tr -dc A-Za-z0-9 | head -c 16`
sed -i "s|#MYSQLUSER#|${PROXSCH_DB_USER}|g" ./.env
PROXSCH_DB_PASS=`head /dev/urandom | tr -dc A-Za-z0-9 | head -c 32`
sed -i "s|#MYSQLPASS#|${PROXSCH_DB_PASS}|g" ./.env

# Get our git hash for our version tag
GIT_HASH=`git rev-parse --short HEAD`
sed -i "s|#GITHASH#|${GIT_HASH}|g" ./.env

# Build the new env
if [ "$1" = "dev" ]; then
  docker-compose up --force-recreate --build --remove-orphans
else
  docker-compose up --force-recreate --build --remove-orphans -d
fi

# Nuke the env file
rm ./.env

# We done
exit 0
