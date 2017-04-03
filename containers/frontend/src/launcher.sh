#!/bin/bash
# Launch tool for the prox-scheduler frontend service

# Check for vars or set defaults
if [ -z ${DEBUG+x} ]; then
	DEBUG='false'
fi
if [ -z ${WORKERS+x} ]; then
	WORKERS=3
fi
if [ -z ${MYSQL_HOST+x} ]; then
	MYSQL_HOST='db'
fi
if [ -z ${MYSQL_USER+x} ]; then
	echo "Error, MYSQL_USER not set! Exiting..."
  sleep 60 && exit 1
fi
if [ -z ${MYSQL_PASS+x} ]; then
	echo "Error, MYSQL_PASS not set! Exiting..."
  sleep 60 && exit 1
fi
if [ -z ${MYSQL_DB+x} ]; then
	echo "Error, MYSQL_DB not set! Exiting..."
  sleep 60 && exit 1
fi
if [ -z ${SCHEDULER_DEFAULT_TEMPLATE_ID+x} ]; then
	echo "Error, SCHEDULER_DEFAULT_TEMPLATE_ID not set! Exiting..."
  sleep 60 && exit 1
fi
if [ -z ${BUILD_DIR+x} ]; then
	echo "Error, BUILD_DIR not set! Exiting..."
  sleep 60 && exit 1
fi
if [ -z ${GIT_HASH+x} ]; then
	echo "Error, GIT_HASH not set! Exiting..."
  sleep 60 && exit 1
fi

# Replace vars and move options file if not explicitly set
if [ ! -f ./options.py ]; then
	sed -i "s|#datecode#|$(date +%Y%m%d)-${GIT_HASH}|g" ./options.py.default
	sed -i "s|#dlfolder#|${BUILD_DIR}|g" ./options.py.default
	sed -i "s|#sqlhost#|${MYSQL_HOST}|g" ./options.py.default
	sed -i "s|#sqluser#|${MYSQL_USER}|g" ./options.py.default
	sed -i "s|#sqlpass#|${MYSQL_PASS}|g" ./options.py.default
	sed -i "s|#sqldb#|${MYSQL_DB}|g" ./options.py.default
	sed -i "s|#templateid#|${SCHEDULER_DEFAULT_TEMPLATE_ID}|g" ./options.py.default
	mv ./options.py.default ./options.py
fi

# Launch our application
if [ "${DEBUG,,}" == "false" ]; then
  echo "Starting Frontend in Production"
  gunicorn --workers ${WORKERS} --bind 0.0.0.0:5000 wsgi:app
else
  echo "Starting Frontend in Debug, single worker only!"
  ./frontend.py
fi
