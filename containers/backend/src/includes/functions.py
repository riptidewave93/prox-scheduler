#!/usr/bin/env python3
#
# Used to hold logic functions
#
# Copyright (C) 2017 Chris Blake <chris@servernetworktech.com>
#
# Used to get a dict of HVs, including usage, for parsing.
import random

# Used to schedule an instance and returns the best HV
def PickNode(proxmox, logger, scheduled_creates, sch_settings, instance):
    cluster = []
    logger.debug("PickNode: Requested logic for build with " +
                 str(instance['cpu']) + " cores and " + str(instance['memory']) + " MB of memory.")
    # For each node in cluster
    for node in proxmox.cluster.resources.get(type='node'):
        # Init vars
        reservedmem = reservedcpu = vmcount = inflight = 0

        # Get our hostname, CPU, and Memory usage
        logger.debug(
            "PickNode: Getting stats from Proxmox for " + str(node['node']))
        stats = proxmox.nodes(node['node']).status.get()
        logger.debug("PickNode: Data from proxmox was " + str(stats))

        # Calculate our scheduled memory, and VM count
        for vm in proxmox.nodes(node['node']).qemu.get():
            reservedmem += vm['maxmem']
            reservedcpu += vm['cpus']
            vmcount += 1
        logger.debug("PickNode: Reseved VM resources for node are mem: " +
                     str(reservedmem) + " cpu: " + str(reservedcpu))

        # Is anything that is in flight on this node?
        for task in scheduled_creates:
            if task['backend_hypervisor'] == node['node']:
                logger.debug(
                    "PickNode: Builds in flight, adding data to HV of " + str(node['node']))
                reservedmem += (task['memory'] * 1024 *
                                1024)  # Move from MB to B
                reservedcpu += task['cpu']
                inflight += 1
                vmcount += 1
        logger.debug("PickNode: Final Reseved VM resources for node are mem: " +
                     str(reservedmem) + " cpu: " + str(reservedcpu))

        # Before we even get started on calculations, have we hit any hard
        # caps?
        if sch_settings['max_inflight'] != 0 and inflight >= sch_settings['max_inflight']:
            logger.debug("PickNode: Dropping " +
                         node['node'] + " - Max Inflight cap hit!")
            continue
        elif sch_settings['max_vms'] != 0 and vmcount >= sch_settings['max_vms']:
            logger.debug("PickNode: Dropping " +
                         node['node'] + " - Max VMs cap hit!")
            continue

        # Add data to our dict
        hv = {}
        hv['name'] = node['node']
        hv['load'] = stats['loadavg']
        hv['memory'] = stats['memory']
        hv['cpus'] = stats['cpuinfo']['cpus']

        # Now add computed information
        hv['scheduler'] = {}
        hv['scheduler']['memory'] = {}
        hv['scheduler']['memory']['provisioned'] = reservedmem
        hv['scheduler']['memory']['available'] = (
            stats['memory']['total'] - reservedmem) * sch_settings['mem_op']
        hv['scheduler']['memory']['free'] = hv[
            'memory']['free'] * sch_settings['mem_op']
        hv['scheduler']['memory']['total'] = hv[
            'memory']['total'] * sch_settings['mem_op']
        hv['scheduler']['cpu'] = {}
        hv['scheduler']['cpu']['provisioned'] = reservedcpu
        hv['scheduler']['cpu']['available'] = (
            stats['cpuinfo']['cpus'] - reservedcpu) * sch_settings['cpu_op']
        hv['scheduler']['cpu']['total'] = stats[
            'cpuinfo']['cpus'] * sch_settings['cpu_op']
        hv['scheduler']['weights'] = {}
        hv['scheduler']['weights']['mem'] = (hv['scheduler']['memory'][
                                             'provisioned'] / hv['scheduler']['memory']['total']) * sch_settings['mem_prov_w']
        hv['scheduler']['weights']['mem-real'] = (hv['memory']['used'] / hv['scheduler'][
                                                  'memory']['total']) * sch_settings['mem_real_w']
        hv['scheduler']['weights']['cpu'] = (hv['scheduler']['cpu'][
                                             'provisioned'] / hv['scheduler']['cpu']['total']) * sch_settings['cpu_prov_w']
        hv['scheduler']['weights']['cpu-real'] = (float(hv['load'][1]) / hv['scheduler'][
                                                  'cpu']['total']) * sch_settings['cpu_prov_w']
        hv['scheduler']['weights']['score'] = hv['scheduler']['weights']['mem'] + hv['scheduler'][
            'weights']['mem-real'] + hv['scheduler']['weights']['cpu'] + hv['scheduler']['weights']['cpu-real']

        # Debug info
        logger.debug(
            "PickNode: " + hv['name'] + " done with scheduler logic of " + str(hv['scheduler']))

        # Now for global nulls - If our VM is bigger than the HV can handle
        if hv["cpus"] < instance['cpu']:
            logger.debug("PickNode: Dropping " +
                         hv['name'] + " due to CPU request under HV CPU count.")
            continue
        elif hv['scheduler']['memory']['total'] < (instance['memory'] * 1024 * 1024):
            logger.debug("PickNode: Dropping " +
                         hv['name'] + " due to mem request under HV mem OP count.")
            continue

        # Nulls for things that are full
        if (hv['scheduler']['memory']['available'] - (instance['memory'] * 1024 * 1024)) <= 0:
            logger.debug("PickNode: Dropping " +
                         hv['name'] + " as this build needs more memory than available.")
            continue
        if hv['scheduler']['cpu']['available'] - instance['cpu'] <= 0:
            logger.debug("PickNode: Dropping " +
                         hv['name'] + " as this build needs more CPU than available.")
            continue

        # Add our HV to our return list
        cluster.append(hv)

    # Now that we have our cluster, did we get any nodes?
    if not cluster:
        raise Exception(
            "PickNode: Error in scheduler, no nodes returned! Are you requesting something too big?")

    # Debug our final scores
    for node in cluster:
        logger.debug("PickNode: " + node['name'] + " had score of " +
                     str(node['scheduler']['weights']['score']))

    # Grab based on lowest total winning score
    selected_node = sorted(cluster, key=lambda k: k['scheduler'][
                           'weights']['score'])[0]['name']
    logger.debug("PickNode: Returning " + selected_node + " as target node.")

    return selected_node

# Used to find the next, lowest, VM ID.
def GetNextVMID(prox):
    return int(prox.cluster.nextid.get())

# Used to find a VM based on it's ID or name (need this when cloning)
def FindVM(proxmox, needle):
    for node in proxmox.cluster.resources.get(type='node'):
        for vm in proxmox.nodes(node['node']).qemu.get():
            if isinstance(needle, int):
                if vm["vmid"] == needle:
                    return node, vm
            elif isinstance(needle, str):
                if vm["name"] == needle:
                    return node, vm
    # Return empty if not found
    return False, False
