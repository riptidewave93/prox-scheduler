#!/bin/bash
# Launch tool for the prox-scheduler backend service

# Check for vars or set defaults
if [ -z ${DEBUG+x} ]; then
	DEBUG="false"
fi
if [ -z ${BUILD_DIR+x} ]; then
	echo "Error, BUILD_DIR is not set!"
  sleep 60 && exit 1
fi
if [ -z ${MYSQL_HOST+x} ]; then
	echo "Error, MYSQL_HOST is not set!"
  sleep 60 && exit 1
fi
if [ -z ${MYSQL_DB+x} ]; then
	echo "Error, MYSQL_DB is not set!"
  sleep 60 && exit 1
fi
if [ -z ${MYSQL_USER+x} ]; then
	echo "Error, MYSQL_USER is not set!"
  sleep 60 && exit 1
fi
if [ -z ${MYSQL_PASS+x} ]; then
	echo "Error, MYSQL_PASS is not set!"
  sleep 60 && exit 1
fi
if [ -z ${PROXMOX_USERNAME+x} ]; then
  echo "Error, PROXMOX_USERNAME is not set!"
  sleep 60 && exit 1
fi
if [ -z ${PROXMOX_PASSWORD+x} ]; then
  echo "Error, PROXMOX_PASSWORD is not set!"
  sleep 60 && exit 1
fi
if [ -z ${PROXMOX_TEMPLATE_ID+x} ]; then
  echo "Error, PROXMOX_TEMPLATE_ID is not set!"
  sleep 60 && exit 1
fi
if [ -z ${PROXMOX_DEFAULT_STORAGE+x} ]; then
  PROXMOX_DEFAULT_STORAGE="None"
else
  PROXMOX_DEFAULT_STORAGE="\"${PROXMOX_DEFAULT_STORAGE}\""
fi
if [ -z ${SSH_USER+x} ]; then
  SSH_USER="root"
fi
if [ -z ${SSH_PORT+x} ]; then
  SSH_PORT="22"
fi
if [ -z ${MAX_THREADS+x} ]; then
	echo "Error, MAX_THREADS is not set!"
  sleep 60 && exit 1
fi
if [ -z ${MAX_SCHEDULED_TASKS+x} ]; then
	echo "Error, MAX_SCHEDULED_TASKS is not set!"
  sleep 60 && exit 1
fi
if [ -z ${SCH_MEM_OP_RATIO+x} ]; then
	echo "Error, SCH_MEM_OP_RATIO is not set!"
	sleep 60 && exit 1
fi
if [ -z ${SCH_CPU_OP_RATIO+x} ]; then
	echo "Error, SCH_CPU_OP_RATIO is not set!"
  sleep 60 && exit 1
fi
if [ -z ${SCH_MEM_PROV_WEIGHT+x} ]; then
	echo "Error, SCH_MEM_PROV_WEIGHT is not set!"
  sleep 60 && exit 1
fi
if [ -z ${SCH_CPU_PROV_WEIGHT+x} ]; then
	echo "Error, SCH_CPU_PROV_WEIGHT is not set!"
  sleep 60 && exit 1
fi
if [ -z ${SCH_REAL_MEM_WEIGHT+x} ]; then
	echo "Error, SCH_REAL_MEM_WEIGHT is not set!"
  sleep 60 && exit 1
fi
if [ -z ${SCH_REAL_CPU_WEIGHT+x} ]; then
	echo "Error, SCH_REAL_CPU_WEIGHT is not set!"
  sleep 60 && exit 1
fi
if [ -z ${SCH_MAX_INFLIGHT_ON_NODE+x} ]; then
	echo "Error, SCH_MAX_INFLIGHT_ON_NODE is not set!"
  sleep 60 && exit 1
fi
if [ -z ${SCH_MAX_VMS_ON_NODE+x} ]; then
	echo "Error, SCH_MAX_VMS_ON_NODE is not set!"
  sleep 60 && exit 1
fi

# Replace vars and move options file if not explicitly set
if [ ! -f ./options.py ]; then
  # Do we want to run in debug?
  if [ "${DEBUG,,}" == "false" ]; then
    sed -i "s|#debug#|False|g" ./options.py.default
  else
    sed -i "s|#debug#|True|g" ./options.py.default
  fi
	sed -i "s|#dlfolder#|${BUILD_DIR}|g" ./options.py.default
  sed -i "s|#proxmoxuser#|${PROXMOX_USERNAME}|g" ./options.py.default
  sed -i "s|#proxmoxpass#|${PROXMOX_PASSWORD}|g" ./options.py.default
	sed -i "s|#mysqlhost#|${MYSQL_HOST}|g" ./options.py.default
	sed -i "s|#mysqluser#|${MYSQL_USER}|g" ./options.py.default
	sed -i "s|#mysqlpass#|${MYSQL_PASS}|g" ./options.py.default
	sed -i "s|#mysqldb#|${MYSQL_DB}|g" ./options.py.default
  sed -i "s|#proxmoxtemplateid#|${PROXMOX_TEMPLATE_ID}|g" ./options.py.default
  sed -i "s|#defaultstorage#|${PROXMOX_DEFAULT_STORAGE}|g" ./options.py.default
  sed -i "s|#sshuser#|${SSH_USER}|g" ./options.py.default
  sed -i "s|#sshport#|${SSH_PORT}|g" ./options.py.default
  sed -i "s|#schedulerlogic#|${SCHEDULER_LOGIC}|g" ./options.py.default
  sed -i "s|#schedulerop#|${SCHEDULER_OP}|g" ./options.py.default
  sed -i "s|#maxthreads#|${MAX_THREADS}|g" ./options.py.default
  sed -i "s|#maxscheduledtasks#|${MAX_SCHEDULED_TASKS}|g" ./options.py.default
	sed -i "s|#mopr#|${SCH_MEM_OP_RATIO}|g" ./options.py.default
	sed -i "s|#copr#|${SCH_CPU_OP_RATIO}|g" ./options.py.default
	sed -i "s|#mpw#|${SCH_MEM_PROV_WEIGHT}|g" ./options.py.default
	sed -i "s|#cpw#|${SCH_CPU_PROV_WEIGHT}|g" ./options.py.default
	sed -i "s|#rmw#|${SCH_REAL_MEM_WEIGHT}|g" ./options.py.default
	sed -i "s|#rcw#|${SCH_REAL_CPU_WEIGHT}|g" ./options.py.default
	sed -i "s|#mion#|${SCH_MAX_INFLIGHT_ON_NODE}|g" ./options.py.default
	sed -i "s|#mvon#|${SCH_MAX_VMS_ON_NODE}|g" ./options.py.default
	mv ./options.py.default ./options.py
fi

# Launch
echo "Starting Backend..."
./backend.py
