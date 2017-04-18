#!/usr/bin/env python3
#
# Copyright (C) 2017 Chris Blake <chris@servernetworktech.com>
#
import ast
from includes.functions import *
import MySQLdb
import MySQLdb.cursors
from options import *
import os
import paramiko
from proxmoxer import ProxmoxAPI
import random
from scp import SCPClient
import shutil
import socket
import string
import time

# This is our CORE class for backend thread tasks!
class Instance(object):
    """
    User Submitted Attributes:
        proxmox = endpoint object
        logger = access to the core logging class
        inst = Instance dict from DB. This is also what we write back on updates
        buildlock = Threading lock object
        run_type = "create" or "destroy"

    Generated Attributes:
        event_node = Stores Proxmox Node of last ran event
        event_id = Stores Proxmox Event ID of last ran event
    """

    def __init__(self, prox, logger, inst, buildlock, run_type):
        self.proxmox = prox
        self.logger = logger
        self.inst = inst
        self.run_type = run_type
        # Only add this object if we are a create
        if run_type == "create":
            self.buildlock = buildlock

    # Get the instance object, used to parse out current settings.
    def Get_Instance_Object(self):
        return self.inst

    # Used to update our entry/info in the DB
    def Save_Instance(self):
        db = MySQLdb.connect(host=sql_host, user=sql_user,
                             passwd=sql_pass, db=sql_db)
        cur = db.cursor(cursorclass=MySQLdb.cursors.DictCursor)

        # So this is a tad jank, but make sure we are not in a "destory" run
        # during a "build"
        query = 'SELECT `state` FROM `instances` WHERE `id` = %(id)s LIMIT 1;'
        cur.execute(query, {'id': self.inst['id']})
        our_state = cur.fetchone()
        self.logger.debug("Save_Instance(): Current " + str(our_state['state']) +
                          ". Requested " + str(self.inst['state']) + ".")

        # If the DB has us in a destroy state and we are create task, NOPE out!
        if ((20 <= our_state['state'] <= 30) or our_state['state'] == 50) and self.run_type == "create":
            cur.close()
            db.close()
            raise Exception("Save_Instance(): Force exit, DB says we are in state " +
                            str(our_state['state']) + " while WE requested to go to " +
                            str(self.inst['state']) + " and are in a create run." +
                            " Do we have a force destroy running?")

        # Now that jank is done, write our entire object to the DB to sync it
        # all
        query = 'UPDATE `instances` SET {}'.format(
            ', '.join('{}=%s'.format(k) for k in self.inst))
        query += ' WHERE `id` = ' + str(self.inst['id']) + ';'
        cur.execute(query, self.inst.values())
        db.commit()
        cur.close()
        db.close()

    # Get the status of our current event
    def Event_Status(self):
        cfg_trys = 0
        while cfg_trys < 5:
            try:
                event = self.proxmox.nodes(self.event_node).tasks(
                    self.event_id).status.get()
            except Exception as e:
                self.logger.debug(
                    "Event_Status: Failed to get Event Status from Proxmox, error of: " + str(e))
                # Sleep and tick up 1
                cfg_trys += 1
                time.sleep(random.randint(0, 2000) / 1000)
                continue
            else:
                break

        # We will only be here if we don't return in the above while case
        if cfg_trys == 5:
            self.inst['state'] = 50
            self.Save_Instance()
            raise Exception(
                "Error querying event status, we timed out on retrys!")

        # If we are here, we got our status
        self.logger.debug("Eventstatus: Raw response = " + str(event))
        if event["status"] == "running":
            return "Running"
        elif event["status"] == "stopped":
            if event["exitstatus"] == "OK":
                return "Done"

        # So if we are here, bad things happened
        self.inst['state'] = 50
        self.Save_Instance()
        return "Error"

    # Build our VM instance
    def Build(self):
        # Are we open to build?
        self.logger.debug("Build: Init, grabbing thread lock.")
        self.buildlock.acquire()

        # If we are here, it's our turn
        self.logger.debug("Build: " + str(self.inst['uuid']) + " has lock.")

        # Query DB for any builds in flight, so we can push them to the
        # scheduler to be aware of.
        db = MySQLdb.connect(host=sql_host, user=sql_user,
                             passwd=sql_pass, db=sql_db)
        cur = db.cursor(cursorclass=MySQLdb.cursors.DictCursor)
        query = "SELECT * FROM `instances` WHERE `state` IN (2,3) AND `backend_hypervisor` IS NOT NULL;"
        cur.execute(query)
        if cur.rowcount == 0:
            resp = []
        else:
            resp = cur.fetchall()
        # Close DB
        cur.close()
        db.close()

        # Were we given a HV to use? If so, skip scheduler
        if self.inst['backend_hypervisor'] is None:
            # Before we can build, get our host from the scheduler logic
            try:
                self.inst['backend_hypervisor'] = PickNode(
                    self.proxmox, self.logger, resp, sch_settings, self.inst)
            except Exception as e:
                self.inst['state'] = 50
                self.Save_Instance()
                # Clear Lock
                self.buildlock.release()
                raise Exception(
                    "Error calling PickNode(), return of " + str(e))
            # Are we still empty?
            if self.inst['backend_hypervisor'] is None:
                self.inst['state'] = 50
                self.Save_Instance()
                # Clear Lock
                self.buildlock.release()
                raise Exception(
                    "No node returned from scheduler. Are you using valid a logic option, or is your build too large?")
            self.logger.debug(
                "Build: Scheduler told us to use node " + self.inst['backend_hypervisor'])

        # Do we have our own template ID, or we using the "Default?"
        if self.inst['template_id'] is None:
            self.inst['template_id'] = prox_template_id

        # Do we know what we are doing for storage yet?
        if self.inst['backend_storage'] is None:
            if default_storage is not None:
                self.inst['backend_storage'] = default_storage

        # Save our changes
        self.Save_Instance()

        # At this point we are safe to allow other builds to run
        self.buildlock.release()
        self.logger.debug("Build: Thread lock removed")

        # Now get info on our template
        tnode, tvm = FindVM(self.proxmox, self.inst['template_id'])
        if tvm is False:
            self.inst['state'] = 50
            self.Save_Instance()
            raise Exception(
                "Requested template ID is not found in your Proxmox environment.")
        else:
            template_node = tnode['node']
            self.logger.debug("Build: Node hosting template " +
                              str(self.inst['template_id']) + " is " + template_node)
        clone_trys = 0
        while clone_trys < 5:
            # Get our ID for our build
            try:
                self.inst['backend_instance_id'] = GetNextVMID(self.proxmox)
            except Exception as e:
                self.logger.debug("Build: GetNextVMID exception of " + str(e))
                # Sleep and tick up 1
                clone_trys += 1
                time.sleep(random.randint(0, 2000) / 1000)
                continue
            self.Save_Instance()
            self.logger.debug("Build: Setting InstanceID to " +
                              str(self.inst['backend_instance_id']))
            self.event_node = template_node  # We do this for logging
            try:
                if self.inst['backend_storage']:
                    self.event_id = self.proxmox.nodes(template_node).qemu(self.inst['template_id']).clone.post(newid=self.inst[
                        'backend_instance_id'], full=1, name=self.inst['hostname'], target=self.inst['backend_hypervisor'], storage=self.inst['backend_storage'])
                else:
                    self.event_id = self.proxmox.nodes(template_node).qemu(self.inst['template_id']).clone.post(newid=self.inst[
                        'backend_hypervisor'], full=1, name=self.inst['hostname'], target=self.inst['backend_hypervisor'])
            except Exception as e:
                self.logger.debug("Build: Clone exception of " + str(e))
                # Sleep and tick up 1
                clone_trys += 1
                time.sleep(random.randint(0, 2000) / 1000)
                continue
            else:
                break

        # We will only be here if we don't return in the above while case
        if clone_trys == 5:
            self.inst['state'] = 50
            self.Save_Instance()
            raise Exception(
                "Error submitting Clone event, we timed out on retrys!")

        self.logger.debug("Build: Clone sent, event ID is " + self.event_id)
        self.inst['state'] = 3
        self.Save_Instance()
        return True

    # Resize to our requested size
    def Resize(self):
        # Get our current config for the instance
        cfg_trys = 0
        while cfg_trys < 5:
            try:
                cfg = self.proxmox.nodes(self.inst['backend_hypervisor']).qemu(
                    self.inst['backend_instance_id']).config.get()
            except Exception as e:
                self.logger.debug(
                    "Resize: Initial config pull exception of " + str(e))
                # Sleep and tick up 1
                cfg_trys += 1
                time.sleep(random.randint(0, 2000) / 1000)
                continue
            else:
                break

        # We will only be here if we don't return in the above while case
        if cfg_trys == 5:
            self.inst['state'] = 50
            self.Save_Instance()
            raise Exception(
                "Error querying info for Resize event, we timed out on retrys!")

        bootdisk = cfg["bootdisk"]
        self.logger.debug("Resize: Got bootdisk of " + cfg["bootdisk"])

        # Set memory & cores
        cfg_trys = 0
        while cfg_trys < 5:
            try:
                self.proxmox.nodes(self.inst['backend_hypervisor']).qemu(self.inst[
                    'backend_instance_id']).config.put(memory=self.inst['memory'], cores=self.inst['cpu'])
            except Exception as e:
                self.logger.debug(
                    "Resize: Resize CPU/Memory exception of " + str(e))
                # Sleep and tick up 1
                cfg_trys += 1
                time.sleep(random.randint(0, 2000) / 1000)
                continue
            else:
                break

        # We will only be here if we don't return in the above while case
        if cfg_trys == 5:
            self.inst['state'] = 50
            self.Save_Instance()
            raise Exception(
                "Error submitting CPU/Memory resize event, we timed out on retrys!")

        self.logger.debug("Resize: Set the following settings. Mem=" +
                          str(self.inst['memory']) + " CPU=" + str(self.inst['cpu']))

        # Resize disk if we got a option that is the same, or larger than the
        # template
        cds = int(cfg[bootdisk].split(",size=", 1)[1].strip("G"))
        if cds > self.inst['disk']:
            self.inst['state'] = 50
            self.Save_Instance()
            raise Exception("Error, disk resize smaller than original disk!")
        cfg_trys = 0  # Reset for reuse
        while cfg_trys < 5:
            try:
                self.proxmox.nodes(self.inst['backend_hypervisor']).qemu(self.inst[
                    'backend_instance_id']).resize.put(disk=bootdisk, size=str(self.inst['disk']) + "G")
            except Exception as e:
                self.logger.debug("Resize: Disk Resize exception of " + str(e))
                # Sleep and tick up 1
                cfg_trys += 1
                time.sleep(random.randint(0, 2000) / 1000)
                continue
            else:
                break

        # We will only be here if we don't return in the above while case
        if cfg_trys == 5:
            self.inst['state'] = 50
            self.Save_Instance()
            raise Exception(
                "Error submitting Disk resize event, we timed out on retrys!")

        self.logger.debug("Resize: Set Disk size to " +
                          str(self.inst['disk']) + "G")
        self.inst['state'] = 4  # Set to resizing
        self.Save_Instance()
        return True

    # Apply our userdata to the description
    def Userdata(self):
        # First thing first, load SSH key from local disk
        ourkey = os.path.expanduser("~/.ssh/id_rsa.pub")
        if os.path.isfile(ourkey):
            with open(ourkey, 'r') as keyfile:
                ssh_public_key = keyfile.read().replace('\n', '')

        # Load our userdata in, as we don't use the frontend view table.
        db = MySQLdb.connect(host=sql_host, user=sql_user,
                             passwd=sql_pass, db=sql_db)
        cur = db.cursor(cursorclass=MySQLdb.cursors.DictCursor)
        query = "SELECT `userdata` FROM `instance_userdata` WHERE `instance_uuid` = %(uuid)s LIMIT 1;"
        cur.execute(query, {'uuid': self.inst['uuid']})
        resp = cur.fetchall()
        # Close DB
        cur.close()
        db.close()

        # Do we have an SSH key? If so, append if we support it in our userdata
        if ssh_public_key != "" and ssh_public_key is not None:
            # We do this is our cursor is a dict with 1 item as a dict.
            userdata = str(resp[0]['userdata']).replace(
                "{PSCHED-SSH-KEY}", ssh_public_key)

        # Get our current userdata for the instance, and apply our stuff
        cfg_trys = 0
        while cfg_trys < 5:
            try:
                tmp_desc = self.proxmox.nodes(self.inst['backend_hypervisor']).qemu(self.inst['backend_instance_id']).config.get()[
                    'description'] + "\n" + ud_start_flag + "\n" + userdata + "\n" + ud_end_flag
            except Exception as e:
                self.logger.debug(
                    "Userdata: Query instance notes exception of " + str(e))
                # Sleep and tick up 1
                cfg_trys += 1
                time.sleep(random.randint(0, 2000) / 1000)
                continue
            else:
                break

        # We will only be here if we don't return in the above while case
        if cfg_trys == 5:
            self.inst['state'] = 50
            self.Save_Instance()
            raise Exception(
                "Error querying instance notes, we timed out on retrys!")

        # Send new info to proxmox
        cfg_trys = 0
        while cfg_trys < 5:
            try:
                self.proxmox.nodes(self.inst['backend_hypervisor']).qemu(
                    self.inst['backend_instance_id']).config.put(description=tmp_desc)
            except Exception as e:
                self.logger.debug(
                    "Userdata: Set userdata exception of " + str(e))
                # Sleep and tick up 1
                cfg_trys += 1
                time.sleep(random.randint(0, 2000) / 1000)
                continue
            else:
                break

        # We will only be here if we don't return in the above while case
        if cfg_trys == 5:
            self.inst['state'] = 50
            self.Save_Instance()
            raise Exception("Error setting userdata, we timed out on retrys!")
        return True

    # Power on our instance
    def Start(self):
        self.event_node = self.inst['backend_hypervisor']
        prox_trys = 0
        while prox_trys < 5:
            try:
                self.event_id = self.proxmox.nodes(self.inst['backend_hypervisor']).qemu(
                    self.inst['backend_instance_id']).status.start.post()
            except Exception as e:
                self.logger.debug("Start: start.post() exception of " + str(e))
                # Sleep and tick up 1
                prox_trys += 1
                time.sleep(random.randint(0, 2000) / 1000)
                continue
            else:
                break

        # If we failed to remove 5x times, raise exception
        if prox_trys == 5:
            self.inst['state'] = 50
            self.Save_Instance()
            raise Exception("Start: Hit timeout trying to startup instance!")

        # At this point, event was sent. Monitor it.
        while True:
            stat = self.Event_Status()
            if stat == "Running":
                time.sleep(2)
                continue
            elif stat == "Done":
                self.logger.debug(
                    "Start: Booted VM, event ID is " + self.event_id)
                self.inst['state'] = 5  # Set as "Powering On"
                self.Save_Instance()
                return True
            elif stat == "Error":
                self.inst['state'] = 50
                self.Save_Instance()
                raise Exception(
                    "Failed to power on VM, Proxmox returned error on event!")

    # Used to get the IP of an instance, verifies a build has Started
    def GetIP(self):
        # Unlike other fuctions, we do this first, as we loop within this
        # function
        self.inst['state'] = 6  # Set as "Provisioning"
        self.Save_Instance()
        # Start the fun
        self.logger.debug("GetIP: Watching for an IP address...")
        # Inital while loop, so we can run til we get the IP
        master_loop = 0
        while master_loop < 60:
            # Try to get the IP
            prox_trys = 0
            while prox_trys < 5:
                try:
                    cfg = self.proxmox.nodes(self.inst['backend_hypervisor']).qemu(
                        self.inst['backend_instance_id']).config.get()['description']
                except Exception as e:
                    self.logger.debug(
                        "GetIP: Get Description exception of " + str(e))
                    # Sleep and tick up 1
                    prox_trys += 1
                    time.sleep(random.randint(0, 2000) / 1000)
                    continue
                else:
                    break

            # We will only be here if we don't return in the above while case
            if prox_trys == 5:
                self.inst['state'] = 50
                self.Save_Instance()
                raise Exception(
                    "Error getting VM description, we ran out of retries!")

            # At this point, cfg is set but we need to check if it has our IP
            # yet.
            for line in cfg.split("\n"):
                if "IP = " in line:
                    self.inst['ip'] = line.strip()[5:]  # Strip off 'IP = '
                    self.logger.debug(
                        "GetIP: IP found, instance is at " + self.inst['ip'])
                    self.Save_Instance()
                    return True  # Fully exit out of this function GetIP()

            # Retry if we did not get our IP
            if self.inst['ip'] is None:
                master_loop += 1
                time.sleep(2)
                continue

        # If we are here, we failed out of master, which means we failed.
        self.inst['state'] = 50
        self.Save_Instance()
        raise Exception("Error getting IP, we timed out on our checks!!")

    # Used to get the status of the build in the instance
    def BuildStatus(self):
        # First we set our state, as at this point we have our IP
        self.inst['state'] = 7  # Set as "Running Build"
        self.Save_Instance()

        # Define SSH goodies
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.load_system_host_keys()

        # Loop so we can monitor from this function, because fuck adding jank
        # to backend.py
        loop_counter = 0
        while True:
            # Attempt our connection
            try:
                ssh.connect(self.inst['ip'], ssh_port, ssh_user, timeout=3)
            except Exception as e:
                # Did we except? Make sure it's a known message we can see
                msgs = ["Unable to connect",
                        "No existing session", "Authentication failed"]
                for error in msgs:
                    if error in str(e):
                        ssh.close()  # Cleanup
                        time.sleep(1)  # zzz to prevent racing
                        continue
                # if we are here, we hit an unknown error. Have we been here
                # too many times?
                if loop_counter > 10:
                    ssh.close()  # Cleanup
                    self.inst['state'] = 50
                    self.Save_Instance()
                    raise Exception(
                        "Error SSHing into droplet repeatedly, last error of " + str(e))

                # Count up
                loop_counter += 1
                continue
            else:
                # We can SSH!
                self.logger.debug("Buildstatus: SSH connection started.")
                # Start another loop for progress checking...
                loop_counter = 0  # We reset this for our usage
                while True:
                    # Check our flag file for status updates
                    try:
                        stdin, stdout, stderr = ssh.exec_command(
                            "cat " + build_flagfile, timeout=3)
                    except socket.error as e:
                        # Does this happen 2 often?
                        if loop_counter > 30:
                            ssh.close()  # Cleanup
                            self.inst['state'] = 50
                            self.Save_Instance()
                            raise Exception(
                                "Error catting build status file, last error of " + str(e))
                        # Just try again
                        loop_counter += 1
                        time.sleep(2)
                        continue
                    except Exception as e:
                        # we should not be here
                        self.inst['state'] = 50
                        self.Save_Instance()
                        raise Exception(
                            "Error with SSH connection, recieved an error of: " + str(e))

                    # Parse out the output from SSH
                    cmdout = stdout.read().decode("utf-8")
                    cmderr = stderr.read().decode("utf-8")
                    self.logger.debug("Buildstatus: stdout: " + cmdout)
                    self.logger.debug("Buildstatus: stderr: " + cmderr)
                    if "No such file or directory" in cmderr:
                        # Still building, just sleep & loop
                        time.sleep(5)
                        continue
                    elif "true" in cmdout:
                        # We finished! close SSH and return
                        self.inst['backend_build_state'] = "success"
                        ssh.close()
                        return True
                    elif "false" in cmdout:
                        # We done, but with error. close/return
                        self.inst['backend_build_state'] = "failed"
                        ssh.close()
                        return True
                    else:
                        ssh.close()
                        self.inst['state'] = 50
                        self.Save_Instance()
                        raise Exception(
                            "Error with SSH connection. stdout: " + cmdout + "\nstderr:" + cmderr)

    # Download our files from the instance
    def Download(self):
        # Start by setting a DL state
        self.inst['state'] = 9  # Downloading
        self.Save_Instance()

        # Do we have a temp folder locally we can store the files?
        savedir = download_dir + '/' + self.inst['uuid']
        if not os.path.exists(savedir):
            os.makedirs(savedir, exist_ok=True)
            self.logger.debug("Download: Made save dir of " + savedir)

        # Are we in good, or error state? If error, DL error files
        our_dls = ast.literal_eval(self.inst['downloads'])
        if self.inst['backend_build_state'] == "failed":
            our_dls = ['/var/log/cloud-init-output.log', '/var/log/syslog']

        # Before we start the downloads, open up an SSH session
        # SSH and check status
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.load_system_host_keys()

        # Loop so we can monitor from this function, because fuck adding jank
        # to backend.py
        loop_counter = 0
        while True:
            # Attempt our connection
            try:
                ssh.connect(self.inst['ip'], ssh_port, ssh_user, timeout=3)
            except Exception as e:
                # Did we except? Make sure it's a known message we can see
                msgs = ["Unable to connect",
                        "No existing session", "Authentication failed"]
                for error in msgs:
                    if error in str(e):
                        ssh.close()  # Cleanup
                        time.sleep(1)  # zzz to prevent racing
                        continue
                # if we are here, we hit an unknown error. Have we been here
                # too many times?
                if loop_counter > 10:
                    ssh.close()  # Cleanup
                    self.inst['state'] = 50
                    self.Save_Instance()
                    raise Exception(
                        "Error SSHing into droplet repeatedly, last error of " + str(e))

                # Count up
                loop_counter += 1
                continue
            else:
                # We connected, carry on to SCP
                for dl in ast.literal_eval(self.inst['downloads']):
                    with SCPClient(ssh.get_transport(), socket_timeout=30) as scp:
                        self.logger.debug(
                            "Download: Downloading file/folder of " + dl)
                        try:
                            scp.get(dl, savedir, recursive=True)
                        except Exception as e:
                            self.inst['state'] = 50
                            self.Save_Instance()
                            raise Exception(
                                "Error with SCP Download, recieved an error of: " + str(e))
                        finally:
                            # This should not be needed with the "with"
                            # statement, but play it safe
                            scp.close()
            finally:
                ssh.close()

            # If we are here, break out of the loop
            break

        # We done here
        return True

    # Compress our build
    def Compress(self):
        # Set our state
        self.inst['state'] = 10  # Compressing
        self.Save_Instance()

        # Do we have downloads?
        tempdir = download_dir + '/' + self.inst['uuid']
        if not os.path.exists(tempdir):
            self.inst['state'] = 50
            self.Save_Instance()
            raise Exception("Error, temp directory of " +
                            tempdir + " does not exist!")

        # Compress what we have
        self.logger.debug('Compress: Running ' + 'tar -czf ' +
                          tempdir + '.tar.gz' + ' -C ' + tempdir + ' .')
        try:
            os.system('tar -czf ' + tempdir +
                      '.tar.gz' + ' -C ' + tempdir + ' .')
        except Exception as e:
            self.inst['state'] = 50
            self.Save_Instance()
            raise Exception(
                "Error creating tar.gz of downloaded files, error of " + str(e))

        # Duid we compress?
        if os.path.exists(download_dir + '/' + self.inst['uuid'] + '.tar.gz'):
            self.logger.debug(
                'Compress: Successfully compressed build at ' + tempdir + '.tar.gz')
        else:
            self.inst['state'] = 50
            self.Save_Instance()
            raise Exception("Error creating tar.gz of downloaded files!")
        # Tar was created, remove tmp dir for our build as we now have the tar.
        shutil.rmtree(tempdir + '/')

    # Used to set the final build state
    def SetBuildState(self):
        # We are only called after compress, so we should be safe with this
        # logic
        if self.inst['backend_build_state'] == "success":
            self.logger.debug('SetBuildState: Setting build as Success')
            self.inst['state'] = 11  # Build Complete
        elif self.inst['backend_build_state'] == "failed":
            self.logger.debug('SetBuildState: Setting build as Failure')
            self.inst['state'] = 12  # Build Failed
        else:
            self.inst['state'] = 50
            self.Save_Instance()
            raise Exception("Error, unknown state of " +
                            str(self.inst['backend_build_state']))

        # Save and return
        self.Save_Instance()
        return True

    # Shutdown instance
    def Shutdown(self):
        prox_trys = 0
        self.event_node = self.inst['backend_hypervisor']
        while prox_trys < 5:
            try:
                self.event_id = self.proxmox.nodes(self.inst['backend_hypervisor']).qemu(
                    self.inst['backend_instance_id']).status.stop.post()
            except Exception as e:
                self.logger.debug(
                    "Shutdown: shutdown.post() exception of " + str(e))
                # Sleep and tick up 1
                prox_trys += 1
                time.sleep(random.randint(0, 2000) / 1000)
                continue
            else:
                break

        # If we failed to remove 5x times, raise exception
        if prox_trys == 5:
            self.inst['state'] = 50
            self.Save_Instance()
            raise Exception(
                "Shutdown: Hit timeout trying to shutdown instance!")

        # At this point, event was sent. Monitor it.
        while True:
            stat = self.Event_Status()
            if stat == "Running":
                time.sleep(2)
                continue
            elif stat == "Done":
                self.logger.debug(
                    "Shutdown: Stopped VM, event ID is " + self.event_id)
                self.inst['state'] = 22
                self.Save_Instance()
                return True
            elif stat == "Error":
                self.inst['state'] = 50
                self.Save_Instance()
                raise Exception(
                    "Failed to power off VM, Proxmox returned error on event!")

    # Destroy our instance
    def Destroy(self):
        self.inst['state'] = 23  # Start by setting our state as "Destroying"
        self.Save_Instance()
        self.event_node = self.inst['backend_hypervisor']

        # First is master loop to ensure re-trys can be done
        rm_master = 0
        while rm_master < 3:
            # Loop for sending event
            rm_trys = 0
            while rm_trys < 5:
                try:
                    self.event_id = self.proxmox.nodes(self.inst['backend_hypervisor']).qemu(
                        self.inst['backend_instance_id']).delete()
                except Exception as e:
                    self.logger.debug(
                        "Destroy: delete() exception of " + str(e))
                    # Sleep and tick up 1
                    rm_trys += 1
                    time.sleep(random.randint(0, 2000) / 1000)
                    continue
                else:
                    break

            # If we failed to remove 5x times, raise exception
            if rm_trys == 5:
                self.inst['state'] = 50
                self.Save_Instance()
                raise Exception(
                    "Destroy: Hit timeout trying to destroy instance!")

            # At this point, event was sent. Monitor it.
            while True:
                stat = self.Event_Status()
                if stat == "Running":
                    time.sleep(2)
                    continue
                elif stat == "Done":
                    self.logger.debug(
                        "Destroy: VM Destroyed, event ID is " + self.event_id)
                    self.inst['state'] = 24
                    self.Save_Instance()
                    # Does our download tar exist for this instance?
                    # If so remove it to clear up space
                    if os.path.exists(download_dir + '/' + self.inst['uuid'] + '.tar.gz'):
                        os.remove(download_dir + '/' +
                                  self.inst['uuid'] + '.tar.gz')
                    return True
                elif stat == "Error":
                    self.inst['state'] = 50
                    self.Save_Instance()
                    raise Exception(
                        "Failed to destroy VM, Proxmox returned error on event!")
