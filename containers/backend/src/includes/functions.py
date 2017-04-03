#!/usr/bin/env python3
#
# Used to hold logic functions
#
# Copyright (C) 2017 Chris Blake <chris@servernetworktech.com>
#
# Used to get a dict of HVs, including usage, for parsing.
import random

# Used to get the nodes of our cluster, and return an array the scheduler can use
def GetNodes(proxmox,logger,scheduled_creates,option,op,build_mem,build_cpu):
    cluster=[]
    logger.debug("GetNodes: Requested logic for build with " + str(build_cpu) + " cores and " + str(build_mem) + " MB of memory.")
    # For each node in cluster
    for node in proxmox.cluster.resources.get(type='node'):
        # Init vars
        reservedmem = reservedcpu = vmcount = 0

        # Get our hostname, CPU, and Memory usage
        logger.debug("GetNodes: Getting stats from Proxmox for " + str(node['node']))
        stats = proxmox.nodes(node['node']).status.get()
        logger.debug("GetNodes: Data from proxmox was " + str(stats))

        # Calculate our scheduled memory, and VM count
        for vm in proxmox.nodes(node['node']).qemu.get():
            reservedmem += vm["maxmem"]
            reservedcpu += vm["cpus"]
            vmcount += 1
        logger.debug("GetNodes: Reseved VM resources for node are mem: " + str(reservedmem) + " cpu: " + str(reservedcpu))

        # Is anything that is in flight on this node?
        for task in scheduled_creates:
            if task['backend_hypervisor'] == node["node"]:
                logger.debug("GetNodes: Builds in flight, adding data to HV of " + str(node["node"]))
                reservedmem += (task["memory"] * 1024 * 1024) # Move from MB to B
                reservedcpu += task["cpu"]
                vmcount += 1
        logger.debug("GetNodes: Final Reseved VM resources for node are mem: " + str(reservedmem) + " cpu: " + str(reservedcpu))

        # Add data to our dict
        hv={}
        hv["name"] = node["node"]
        hv["load"] = stats["loadavg"]
        hv["memory"] = stats["memory"]
        hv["cpus"] = stats["cpuinfo"]["cpus"]

        # Now add computed information
        hv["scheduler"] = {}
        hv["scheduler"]["memory"] = {}
        hv["scheduler"]["memory"]["provisioned"] = reservedmem
        hv["scheduler"]["memory"]["available"] = (stats["memory"]["total"] - reservedmem) * op
        hv["scheduler"]["memory"]["free"] = hv["memory"]["free"] * op
        hv["scheduler"]["memory"]["total"] = hv["memory"]["total"] * op
        hv["scheduler"]["cpu"] = {}
        hv["scheduler"]["cpu"]["provisioned"] = reservedcpu
        hv["scheduler"]["cpu"]["available"] = (stats["cpuinfo"]["cpus"] - reservedcpu) * op
        hv["scheduler"]["cpu"]["total"] = stats["cpuinfo"]["cpus"] * op

        # Debug info
        logger.debug("GetNodes: Node done, data of " + str(hv))

        # Here we do some basic nulling options to reject hosts from being an option
        if option == "mem":
            # Do we have enough mem? with OP applied. (this is a bit agressive)
            if hv["scheduler"]["memory"]["available"] < (build_mem * 1024 * 1024):
                logger.debug("GetNodes: Droping node due to mem request under OP mem limit.")
                continue
        elif option == "cpus":
            # Do we have enough CPUs? with OP applied.
            if hv["scheduler"]["cpu"]["available"] < build_cpu:
                logger.debug("GetNodes: Droping node due to CPU request under OP CPU limit.")
                continue

        # Now for global nulls
        # If our VM is bigger than the HV can handle
        if hv["cpus"] < build_cpu:
            logger.debug("GetNodes: Droping node due to CPU request under HV CPU count.")
            continue
        elif hv["memory"]["total"] < (build_mem * 1024 * 1024):
            logger.debug("GetNodes: Droping node due to mem request under HV mem count.")
            continue

        # Add our HV to our return list
        logger.debug("GetNodes: appending " + str(node['node']))
        cluster.append(hv)

    # Return our environment
    return cluster

# Used to find what node we can use, based on resource utilization
def PickNode(proxmox,logger,scheduled_creates,option,op,build_mem,build_cpu):
    # Get our nodes
    cluster = GetNodes(proxmox,logger,scheduled_creates,option,op,build_mem,build_cpu)
    logger.debug("PickNode: Returned HV scheduler logic was " + str(cluster))

    # Did we get any nodes?
    if not cluster:
        raise Exception("Error in scheduler, no nodes returned! Are you requesting something too big?")

    logger.debug("PickNode: Running through schedulder logic of " + option)
    # Our available scheduler options & logic
    switcher = {
        "mem": sorted(cluster, key=lambda k: k["scheduler"]["memory"]["available"], reverse=True)[0],
        "realmem": sorted(cluster, key=lambda k: k["scheduler"]["memory"]["free"], reverse=True)[0],
        "load": sorted(cluster, key=lambda k: k['load'][1])[0],
        "cpus": sorted(cluster, key=lambda k: k["scheduler"]["cpu"]["available"], reverse=True)[0],
        "random": sorted(cluster, key=lambda k: random.random())[0],
    }

    return switcher.get(option, {})

# Used to find the next, lowest, VM ID.
def GetNextVMID(prox):
    return int(prox.cluster.nextid.get())

# Used to find a VM based on it's ID or name (need this when cloning)
def FindVM(proxmox,needle):
    if isinstance(needle,int):
        for node in proxmox.cluster.resources.get(type='node'):
            for vm in proxmox.nodes(node['node']).qemu.get():
                if vm["vmid"] == needle:
                    return node, vm
    elif isinstance(needle,str):
        for node in proxmox.cluster.resources.get(type='node'):
            for vm in proxmox.nodes(node['node']).qemu.get():
                if vm["name"] == needle:
                    return node, vm
    return False, False
