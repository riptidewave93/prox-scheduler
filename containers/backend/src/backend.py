#!/usr/bin/env python3
#
# Copyright (C) 2017 Chris Blake <chris@servernetworktech.com>
#
import logging
import MySQLdb
import MySQLdb.cursors
import os
from proxmoxer import ProxmoxAPI
import queue
import random
import requests
import subprocess
import sys
import threading
import time
from includes.functions import *
from includes.instance import Instance
try:
    from options import *
except ImportError:
    print('Error importing options.py. Did you rename and edit options.py.example?')
    sys.exit(1)

# Define function to update a state of an instance in the DB
def UpdateInstanceState(logger, uuid, state):
    db = MySQLdb.connect(host=sql_host, user=sql_user,
                         passwd=sql_pass, db=sql_db)
    cur = db.cursor(cursorclass=MySQLdb.cursors.DictCursor)
    # Update our state for said instance
    query = "UPDATE `instances` SET `state` = %s WHERE `uuid` = %s;"
    cur.execute(query, (state, uuid))
    logger.debug("UpdateInstanceState: Set " + uuid +
                 " to state ID of " + str(state))
    # Save and bail
    db.commit()
    cur.close()
    db.close()

# A "worker" for an instance, this is threaded!!!
def worker():
    while True:
        if itemqueue.empty():
            # Thread is out of tasks
            break
        else:
            # Grab a task from the queue
            binst = itemqueue.get()

        # Start run
        logging.debug("Build Data: " + str(binst))

        # Run Setup
        proxmox = ProxmoxAPI(prox_url, user=prox_user,
                             password=prox_pass, verify_ssl=False)

        # Pick flow based on state
        if binst['state'] == 2:
            # Create Flow
            logging.info("Entering Build Flow for " + binst["uuid"])

            # Create our instance object
            ourrun = Instance(proxmox, logging, binst, buildlock, "create")

            # Create our instance via full clone
            logging.info('VM is Building...')
            try:
                ourrun.Build()
            except Exception as e:
                logging.error("Build() Exception! Message of: " + str(e))
                return 1
            while True:
                time.sleep(3)
                try:
                    stat = ourrun.Event_Status()
                except Exception as e:
                    logging.error("Event_Status() Exception! Message of: " + str(e))
                    return 1
                if stat == "Running":
                    continue
                elif stat == "Done":
                    break
                elif stat == "Error":
                    logging.error("Build Error! Proxmox API returned error.")
                    return 1

            # Move to Resizing
            logging.info('Resizing instance...')
            try:
                ourrun.Resize()
            except Exception as e:
                logging.error("Resize() Exception! Message of: " + str(e))
                return 1

            # Apply our userdata
            logging.info('Applying Userdata...')
            try:
                ourrun.Userdata()
            except Exception as e:
                logging.error("Userdata() Exception! Message of: " + str(e))
                return 1

            # Boot our instance
            logging.info('Booting...')
            try:
                ourrun.Start()
            except Exception as e:
                logging.error("Start() Exception! Message of: " + str(e))
                return 1

            # Get our IP
            logging.info('Getting IP Address...')
            try:
                ourrun.GetIP()
            except Exception as e:
                logging.error("GetIP() Exception! Message of: " + str(e))
                return 1

            # At this point, if we are "NOT" a build let's finish out
            if binst["downloads"] is None:
                UpdateInstanceState(logging, build["uuid"], 8)
                logging.info("Done with " + binst["uuid"])
                return 0

            # Run our Build
            logging.info('Monitoring Build...')
            try:
                ourrun.BuildStatus()
            except Exception as e:
                logging.error("BuildStatus() Exception! Message of: " + str(e))
                return 1

            # Download our Build
            logging.info('Downloading Build...')
            try:
                ourrun.Download()
            except Exception as e:
                logging.error("Download() Exception! Message of: " + str(e))
                return 1

            # Compress our Build
            logging.info('Compressing Build...')
            try:
                ourrun.Compress()
            except Exception as e:
                logging.error("Compress() Exception! Message of: " + str(e))
                return 1

            # Set our Final State
            logging.info('Finalizing...')
            try:
                ourrun.SetBuildState()
            except Exception as e:
                logging.error(
                    "SetBuildState() Exception! Message of: " + str(e))
                return 1

        elif binst['state'] == 21:
            # Destroy
            logging.info("Entering Destroy Flow for " + binst["uuid"])

            # Create our instance object
            ourrun = Instance(proxmox, logging, binst, None, "destroy")

            # First, power off the instance
            try:
                ourrun.Shutdown()
            except Exception as e:
                logging.error("Shutdown() Exception! Message of: " + str(e))
                return 1

            # Remove our instance
            try:
                ourrun.Destroy()
            except Exception as e:
                logging.error("Destroy() Exception! Message of: " + str(e))
                return 1
        else:
            # Any non-scheduler handled starting state goes here
            logging.error("Error, unable to process " +
                          binst['uuid'] + " as it is in state of " + str(binst['state']))
            break

        logging.info("Done with " + binst["uuid"])

# Define our logger, because, logger
if DEBUG:
    logging.basicConfig(level=logging.DEBUG,
                        format='[%(asctime)s] [%(levelname)s] (%(threadName)-10s) %(message)s',
                        )
else:
    logging.basicConfig(level=logging.INFO,
                        format='[%(asctime)s] [%(levelname)s] (%(threadName)-10s) %(message)s',
                        )
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("paramiko").setLevel(logging.WARNING)
    logging.getLogger("proxmoxer").setLevel(logging.WARNING)
logging = logging.getLogger("prox-scheduler-backend")

# Define our queue for builds
itemqueue = queue.Queue()

# Define our queue for Create Locks (prevents racing)
buildlock = threading.Lock()

if __name__ == '__main__':
    # First start, wait for DB to spinup
    logging.info("Backend waiting on DB startup...")
    while True:
        try:
            db = MySQLdb.connect(host=sql_host, user=sql_user,
                                 passwd=sql_pass, db=sql_db)
        except Exception as e:
            time.sleep(5)
        else:
            db.close()
            break
    logging.info("Backend started! Waiting on requests...")
    # Run as a daemon
    while True:
        # Check DB for tasks, limit to our max allowed per run (count x
        # threads)
        db = MySQLdb.connect(host=sql_host, user=sql_user,
                             passwd=sql_pass, db=sql_db)
        cur = db.cursor(cursorclass=MySQLdb.cursors.DictCursor)
        query = "SELECT * FROM `instances` WHERE `state` IN (1,20) LIMIT %(lim)s;"
        cur.execute(
            query, {'lim': (backend_threads * backend_reserved_events)})
        if cur.rowcount == 0:
            # No data, sleep and recheck
            cur.close()
            db.close()
            time.sleep(5)
            continue
        else:
            resp = cur.fetchall()
        # Close DB
        cur.close()
        db.close()

        # For each build...
        for build in resp:
            # If we can take more tasks
            if itemqueue.qsize() < backend_reserved_events:
                logging.debug("Adding " + build["uuid"] + " to queue")
                # Make this ours before we push it up
                if build['state'] == 1:
                    UpdateInstanceState(logging, build["uuid"], 2)
                    build['state'] = 2  # Update locally as well
                elif build['state'] == 20:
                    UpdateInstanceState(logging, build["uuid"], 21)
                    build['state'] = 21  # Update locally as well
                itemqueue.put(build)
            continue

        # Start our threads as needed
        for i in range(backend_threads):
            t = threading.Thread(target=worker)
            t.start()
        # Sleep before we re-loop for new things
        time.sleep(5)
