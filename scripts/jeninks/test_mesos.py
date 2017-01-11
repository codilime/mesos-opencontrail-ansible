#!/usr/bin/env python

import logging
import os
import paramiko
import random
import string
import time

from jinja2 import Environment, PackageLoader
from keystoneauth1 import loading
from keystoneauth1 import session
from novaclient import client


env = Environment(loader=PackageLoader('test_mesos', '.'))
logger = None

DEFAULT_AUTH_URL = 'https://localhost:5000/v2'
DEFAULT_USERNAME = 'admin'
DEFAULT_PASSWORD = 'admin'
DEFAULT_TENANT_NAME = 'admin'
DEFAULT_VERSION = '2.0'
DEFAULT_SSH_USERNAME = 'ubuntu'

OS_IMAGE = 'Ubuntu Server 14.04.4'
OS_SSH_USERNAME = 'ubuntu'
OS_NETWORK_NAME = 'juniper-net'
OS_FLAVOR = 'm1.large'
OS_SECURITY_GROUPS = ['default']
OS_KEY_NAME = 'jenkins-rsa'

DEPLOYER_HOST = 'localhost'
DEPLOYER_USER = 'ubuntu'

INVENOTRY_FILENAME = 'inventory.cluster'

MESOS_ANSIBLE_REPO = 'https://github.com/codilime/mesos-opencontrail-ansible'
MESOS_REPO_BRANCH = 'tests'


class MesosTestServer:
    """Simple class describing a server"""

    def __init__(self, name=''.join(random.SystemRandom().choice(
            string.ascii_uppercase + string.digits) for _ in range(8))):
        self._name = name
        self._ip = ''
        self._id = ''

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, name):
        self._name = name

    @property
    def ip(self):
        return self._ip

    @ip.setter
    def ip(self, ip):
        self._ip = ip

    @property
    def id(self):
        return self._id

    @id.setter
    def username(self, username):
        self._id = id


class MesosCluster:
    """Cluster definition

    This class is what the whole script is working on.

    It contains lists of MesosTestServer objects.
    There are also subnet definitions which are mainly required by
    contrail-3 role of mesos-opencontrail-ansible and are used to fill
    in inventory variables used by that role.
    """

    def __init__(self):
        self._masters = []
        self._gateways = []
        self._nodes = []
        self._subnet = '10.0.0.0/20'
        self._public_subnet = '172.16.8.0/24'
        self._private_subnet = '10.32.0.0/16'
        self._service_subnet = '10.193.0.0/16'
        name = '.'.join([__name__, self.__class__.__name__])
        self._logger = logging.getLogger(name)
        self._logger.setLevel(logging.DEBUG)

    @property
    def logger(self):
        return self._logger

    @property
    def masters(self):
        return self._masters

    @property
    def gateways(self):
        return self._gateways

    @property
    def nodes(self):
        return self._nodes

    @property
    def servers(self):
        return self._masters + self._gateways + self._nodes

    @property
    def subnet(self):
        return self._subnet

    @subnet.setter
    def subnet(self, subnet):
        self._subnet = subnet

    @property
    def public_subnet(self):
        return self._public_subnet

    @public_subnet.setter
    def public_subnet(self, public_subnet):
        self._public_subnet = public_subnet

    @property
    def private_subnet(self):
        return self._private_subnet

    @private_subnet.setter
    def private_subnet(self, private_subnet):
        self._private_subnet = private_subnet

    @property
    def service_subnet(self):
        return self._service_subnet

    @service_subnet.setter
    def service_subnet(self, service_subnet):
        self._service_subnet = service_subnet

    def addMaster(self, master):
        self.logger.debug('Cluster: adding master: ' + master.name)
        self._masters.append(master)

    def addGateway(self, gateway):
        self.logger.debug('Cluster: adding gateway: ' + gateway.name)
        self._gateways.append(gateway)

    def addNode(self, node):
        self.logger.debug('Cluster: adding node: ' + node.name)
        self._nodes.append(node)


def getParamValue(param):
    return os.getenv('OS_'+param, eval('DEFAULT_' + param))


#############################
# OpenStack provisioning part
#############################
def createNovaClient():
    auth_url = getParamValue('AUTH_URL')
    username = getParamValue('USERNAME')
    password = getParamValue('PASSWORD')
    tenant = getParamValue('TENANT_NAME')
    version = getParamValue('VERSION')

    loader = loading.get_plugin_loader('password')
    auth = loader.load_from_options(auth_url=auth_url,
                                    username=username,
                                    password=password,
                                    project_name=tenant)
    sess = session.Session(auth=auth)
    nova = client.Client(version, session=sess)
    return nova


def deleteOSCluster(cluster):
    """Deletes cluster on OpenStack"""
    nova = createNovaClient()
    for server in cluster.servers:
        serverInstance = nova.servers.get(server.id)
        serverInstance.delete()


def createOSCluster(cluster):
    nova = createNovaClient()
    image = nova.images.findall(name=OS_IMAGE)[0]
    flavor = nova.flavors.findall(name=OS_FLAVOR)[0]
    network = nova.networks.findall(label=OS_NETWORK_NAME)[0]
    logger.debug('Creating cluster...')
    for server in cluster.servers:
        srv = nova.servers.create(name=server.name,
                                  image=image,
                                  flavor=flavor,
                                  security_groups=OS_SECURITY_GROUPS,
                                  key_name=OS_KEY_NAME,
                                  nics=[{'net-id': network.id}])
        while len(srv.interface_list()) == 0 or srv.status != 'ACTIVE':
            time.sleep(1)
            srv = nova.servers.get(srv.id)
        server.ip = srv.interface_list()[0].fixed_ips[0]['ip_address']
        server.id = srv.id
        logger.info('Created OS Server <' + server.name + '> ip: |' +
                    server.ip + '|, id: |' + server.id + '|')
    logger.debug('Cluster created.')


def defineOSCluster():
    cluster = MesosCluster()

    cluster.addMaster(MesosTestServer('test-mesos-master-01'))
    cluster.addGateway(MesosTestServer('test-mesos-gateway-01'))
    cluster.addNode(MesosTestServer('test-mesos-node-01'))
    cluster.addNode(MesosTestServer('test-mesos-node-02'))

    return cluster
#############################


def createInventoryFile(cluster):
    inv = env.get_template('inventory.j2')
    render_output = inv.render(cluster=cluster, ssh_user=DEFAULT_SSH_USERNAME)

    tmpdir = os.popen('mktemp -d').read().strip()
    with open(os.path.join(tmpdir, INVENOTRY_FILENAME), 'wb') as f:
        f.write(render_output)
    logger.debug('Inventory file created: ' +
                 os.path.join(tmpdir, INVENOTRY_FILENAME))

    return os.path.join(tmpdir, INVENOTRY_FILENAME)


def prepareWorkingDirDeployer(host, username, ssh, cluster):
    try:
        ssh.connect(host, username=username)
    except:
        logger.error('Failed to connect to: ' + username + '@' + host)
        raise

    inv_file_path = createInventoryFile(cluster)
    _, stdout, _ = ssh.exec_command('mktemp -d')
    remote_tmpdir = stdout.readline().strip()
    logger.debug('Remote temporary directory created: ' + remote_tmpdir)
    logger.debug('Cloning mesos ansibles...')
    _, stdout, stderr = ssh.exec_command('cd ' + remote_tmpdir +
                                         ';git clone --branch ' +
                                         MESOS_REPO_BRANCH + ' ' +
                                         MESOS_ANSIBLE_REPO,
                                         get_pty=True)
    while not stdout.channel.eof_received:
        logger.debug(stdout.readline().strip())
    sftp = ssh.open_sftp()
    logger.debug('Sending inventory file...')
    remote_inv_file_path = os.path.join(remote_tmpdir,
                                        'mesos-opencontrail-ansible/' +
                                        INVENOTRY_FILENAME)
    try:
        sftp.put(inv_file_path, remote_inv_file_path)
    except:
        logger.error('Failed to send local inventory file: ' +
                     inv_file_path +
                     'to remote: ' +
                     remote_inv_file_path)
        raise
    sftp.close()
    # give some time for machines
    time.sleep(10)
    return remote_tmpdir


def runAnsible(host, username, ssh, chdir, playbook):
    try:
        ssh.connect(host, username=username)
    except:
        logger.error('Failed to connect to: ' + username + '@' + host)
        raise

    paramiko.agent.AgentRequestHandler(ssh.get_transport().open_session())
    logger.info(username + '@' + host + ': running playbook <' +
                playbook + '> in directory: ' + chdir)
    _, stdout, stderr = ssh.exec_command('cd ' + chdir +
                                         '; ansible-playbook -i ' +
                                         INVENOTRY_FILENAME +
                                         ' ' + playbook, get_pty=True)
    while not stdout.channel.eof_received:
        logger.info(stdout.readline().strip())
    logger.info('Command exited with status: ' +
                str(stdout.channel.exit_status))


def main():
    global logger
    logging.basicConfig()
    logger = logging.getLogger('test_mesos')
    logger.setLevel(logging.DEBUG)

    testCluster = defineOSCluster()
    createOSCluster(testCluster)

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.load_system_host_keys()

    working_dir = prepareWorkingDirDeployer(DEPLOYER_HOST,
                                            DEPLOYER_USER,
                                            ssh,
                                            testCluster)
    runAnsible(DEPLOYER_HOST, DEPLOYER_USER, ssh,
               working_dir + '/mesos-opencontrail-ansible',
               'resolution.yml')
    runAnsible(DEPLOYER_HOST, DEPLOYER_USER, ssh,
               working_dir + '/mesos-opencontrail-ansible',
               'mesos.yml')
    runAnsible(DEPLOYER_HOST, DEPLOYER_USER, ssh,
               working_dir + '/mesos-opencontrail-ansible',
               'opencontrail.yml')
    runAnsible(DEPLOYER_HOST, DEPLOYER_USER, ssh,
               working_dir + '/mesos-opencontrail-ansible',
               'marathon.yml')
    runAnsible(DEPLOYER_HOST, DEPLOYER_USER, ssh,
               working_dir + '/mesos-opencontrail-ansible',
               'guestbook.yml')

    runAnsible(DEPLOYER_HOST, DEPLOYER_USER, ssh,
               working_dir + '/mesos-opencontrail-ansible',
               'test-mesos.yml')
    runAnsible(DEPLOYER_HOST, DEPLOYER_USER, ssh,
               working_dir + '/mesos-opencontrail-ansible',
               'test-marathon.yml')
    runAnsible(DEPLOYER_HOST, DEPLOYER_USER, ssh,
               working_dir + '/mesos-opencontrail-ansible',
               'test-opencontrail.yml')

    deleteOSCluster(testCluster)
    ssh.close()


if __name__ == '__main__':
    main()
