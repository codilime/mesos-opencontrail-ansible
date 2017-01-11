test_mesos
===================

# Python script for testing mesos with OpenContrail

### Overview

This script is intended to be run by a Jenkins job to be able to deploy a Mesos + OpenContrail cluster and run tests against it.

The intended use uses one Master node, one Gateway node, and 2 Compute nodes

### Usage

Script has a sample implementation of setting up its own test cluster on OpenStack. The script has to be run in set up shell environment with OpenStack variables defined (see `os-openrc.sh.example` file).

Lets see what the main() function does.

First, a cluster object needs to be defined, with a few servers. An example implementation:
```python
def defineOSCluster():
    cluster = MesosCluster()

    cluster.addMaster(MesosTestServer('test-mesos-master-01'))
    cluster.addGateway(MesosTestServer('test-mesos-gateway-01'))
    cluster.addNode(MesosTestServer('test-mesos-node-01'))
    cluster.addNode(MesosTestServer('test-mesos-node-02'))

    return cluster
```

This object is then used to perform all other operations.

The function `createOSCluster(cluster)` takes the cluster object an creates Nova nodes based on the server names. It also fills up the remaining server information by adding the neccessary IP address of the servers and also an ID field.
Such cluster object is then ready to be used by remaining testing code.

### Deployer

The script is based on an idea, that there has to be a deployer machine which will be used to run all the remote commands from. This is a preconfigured jump-host with well known IP address that will run all ansible commands. This can also be defined as `localhost` if the Jenkins slave can function as the deployer.
Remember that deployer needs to have access to cluster servers by their IP value.

### Adaptation to own environments

In order to use any other way of setting up the cluster, all the script really needs is a defined cluster object.
To use it at your own environment, remove:
```python
testCluster = defineOSCluster()
createOSCluster(testCluster)
```
and
```python
deleteOSCluster(testCluster)
```
and replace that with any code that can provide a MesosCluster object will well defined servers.
