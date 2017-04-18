prox-scheduler
====

A scheduler service & endpoint to act as the entry point for builds/creates within a Proxmox Environment. When used correctly, this provides an API endpoint that can be used to provision instances within Proxmox.

Specifically, this is designed for two use cases in mind:
  1. Deploying infrastructure within an Environment
  2. Running "One Off" builds/tests

Setup
----
  * Create a custom Proxmox user and group with the correct permissions to query an environment for information:
    ```
    pveum roleadd PVECloudScheduler -privs "Sys.Audit VM.Audit VM.Allocate VM.Clone VM.PowerMgmt VM.Config.Options VM.Config.Memory VM.Config.CPU VM.Config.Disk Datastore.AllocateSpace"
    pveum groupadd CloudScheduler -comment "Scheduler User Group"
    pveum aclmod / -group CloudScheduler -role PVECloudScheduler
    pveum useradd ProxScheduler@pve -comment "Cloud Scheduler User"
    pveum passwd ProxScheduler@pve
    pveum usermod ProxScheduler@pve -group CloudScheduler
    ```
  * Create a VM Template within Proxmox that has [prox-provision](https://github.com/riptidewave93/prox-provision) installed/configured.
  * Copy compose.env.example to `compose.env.prod` and `compose.env.dev` and edit each as necessary
  * Deploy the service in either production or development Mode
  * Once done, API will be accessable at http://0.0.0.0:5000/. Defaul user/pass of admin/Te$TP@sS1!

Deploy/Upgrade in Development Mode
----
```
./deploy.sh dev
```

Deploy/Upgrade in Production Mode
----
```
./deploy.sh
```

Documentation
----
Documentation for this can be found in the `./docs` folder.

To Do
----
  * Look into moving to celery
  * Add logging to the DB, allow for more verbose errors on any failure event
  * Add storage space check logic (OP ratio for this?)
  * Possibly split out scheduler to it's own container/service?
  * Finish & Cleanup Documentation
