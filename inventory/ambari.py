# Copyright (c) 2018, Michael Hatoum <michael@adaltas.com>
from __future__ import (absolute_import, division, print_function)

import urllib3
import json
from requests.auth import HTTPBasicAuth
import requests
import ast
import os
from ansible.plugins.inventory import BaseInventoryPlugin, Constructable, Cacheable
from ansible.module_utils.common._collections_compat import MutableMapping
from ansible.module_utils._text import to_bytes, to_native, to_text
from ansible.errors import AnsibleParserError, AnsibleError
__metaclass__ = type

DOCUMENTATION = '''
    name: ambari
    plugin_type: inventory
    short_description: ambari inventory source
    requirements:
        - python-ambariclient
    extends_documentation_fragment:
        - inventory_cache
        - constructed
    description:
        - Get inventory hosts from Apache Ambari.
        - Uses a YAML configuration file that ends with ambari.(yml|yaml).
    options:
        hostname:
            description: host name
        port:
            description: port
        username:
            description: username
        password:
            description: password
        protocol:
            description: ambari protocol
            choices: ['http', 'https']
        validate_ssl:
            description: validate ssl
            type: boolean
            choices: [False, True]
        ansible_user:
            description: ssh username
        ansible_ssh_pass:
            description: ssh password
'''
EXAMPLES = '''
plugin: ambari
hostname: ambari-server.makayel.local
port: 8443
username: localuser
password: localpass
protocol: https
validate_ssl: False
ansible_user: nodesuser
ansible_ssh_pass: nodespass
'''


try:
    from ambariclient.client import Ambari
except ImportError:
    raise AnsibleError(
        'The Apache Ambari dynamic inventory plugin requires python-ambariclient (pip3 install python-ambariclient).')


class InventoryModule(BaseInventoryPlugin, Constructable, Cacheable):
    NAME = 'ambari'

    def verify_file(self, path):
        ''' return true/false if this is possibly a valid file for this plugin to consume '''
        valid = False
        if super(InventoryModule, self).verify_file(path):
            # base class verifies that file exists and is readable by current user
            if path.endswith(('.ambari.yaml', '.ambari.yml')):
                valid = True
        return valid

    def parse(self, inventory, loader, path, cache=False):
        # call base method to ensure properties are available for use with other helper methods
        super(InventoryModule, self).parse(inventory, loader, path)

        # this method will parse 'common format' inventory sources and
        # update any options declared in DOCUMENTATION as needed
        config_data = self._read_config_data(path)

        self._parse_config()
        # initialize Apache Ambari client
        self._initialize_client()

        # get cluster name
        _cluster_name = self._get_cluster_name()

        # get services name
        _services_name = self._get_services_name(_cluster_name)

        # get hosts name
        _hosts_name = self._get_hosts_name(_cluster_name)

        # populate groups
        self._populate_groups(_cluster_name, _services_name)

        # populate hosts
        self._populate_hosts(_cluster_name, _services_name, _hosts_name)

        # populate ambari server
        self._populate_ambari(_cluster_name)

        # populate localhost
        self._populate_localhost()

    def _set_config(self, key, env_key, option_key, default):
        '''
        Set key of `config` dict.
        Priority: environment variable, file variable, default value.
        '''
        try:
            self.config[key] = os.environ[env_key]
        except KeyError:
            self.config[key] = self.get_option(option_key) or default

    def _parse_config(self):
        '''Set configuration based on file or environment variables'''
        self.config = {}

        self._set_config('hostname',                   # self.config key
                         'AMBARI_HOSTNAME',            # os env key
                         'hostname',                   # file option key
                         'ambari-host.local')          # default value

        self._set_config('port',
                         'AMBARI_PORT',
                         'port',
                         8443)

        self._set_config('username',
                         'AMBARI_USERNAME',
                         'username',
                         'admin')

        self._set_config('password',
                         'AMBARI_PASSWORD',
                         'password',
                         'admin')

        self._set_config('protocol',
                         'AMBARI_PROTOCOL',
                         'protocol',
                         'http')

        self._set_config('validate_ssl',
                         'AMBARI_VALIDATE_SSL',
                         'validate_ssl',
                         False)

        self._set_config('ansible_user',
                         'ANSIBLE_USER',
                         'ansible_user',
                         None)

        self._set_config('ansible_ssh_pass',
                         'ANSIBLE_SSH_PASS',
                         'ansible_ssh_pass',
                         None)

    ###########################################################################
    # Engine
    ###########################################################################

    def _populate_groups(self, cluster_name, services_name):
        '''
            Populate groups
            :param cluster_name: name of the cluster
            :param services_name: name of the services
        '''
        for service_name in services_name:
            self.inventory.add_group(service_name.lower())

            for component_name in self._get_components_name(cluster_name, service_name):
                self.inventory.add_group(component_name.lower())
                if service_name.lower() != component_name.lower():
                    self.inventory.add_child(
                        service_name.lower(), component_name.lower())

    def _populate_hosts(self, cluster_name, services_name, hosts_name):
        '''
            Populate hosts
            :param cluster_name: name of the cluster
            :param service_name: name of the services
            :param hosts_name: name of the hosts
        '''
        for host_name in hosts_name:
            self.inventory.add_host(host_name)

            configurations = {}

            for service_name in services_name:
                configurations_json = {}
                for service in self._get_service_current_configuration(cluster_name, service_name)['items']:
                    configuration_json = {}
                    for configuration in service['configurations']:
                        configuration_json[configuration['type']
                                           ] = configuration['properties']
                    configurations_json = configuration_json
                configurations[service_name.lower()] = configurations_json

            self.inventory.set_variable(
                host_name, 'configurations', configurations)

            host = self._get_host(host_name)
            self.inventory.set_variable(host_name, 'ansible_host', host_name)
            for field in host.fields:
                if (field.startswith('host') is not True) and (field.startswith('last') is not True) and field != 'desired_configs':
                    self.inventory.set_variable(
                        host_name, field, getattr(host, field))

            if self.config.get('ansible_user'):
                self.inventory.set_variable(
                    host_name, 'ansible_user', self.config.get('ansible_user'))
            if self.config.get('ansible_ssh_pass'):
                self.inventory.set_variable(
                    host_name, 'ansible_ssh_pass', self.config.get('ansible_ssh_pass'))

            for component in self._get_host_components(cluster_name, host_name):
                self.inventory.add_host(
                    host_name,
                    group=component.component_name.lower(),
                    variables={'toto': 'tata'})

    def _populate_ambari(self, _cluster_name):
        '''
            Add the Ambari Server to the inventory file
            :param cluster_name: name of the cluster
        '''
        _group = 'ambari_server'
        _hostname = self.config.get('hostname')
        ambari_config = {}

        self.inventory.add_group(_group)
        self.inventory.add_host(_hostname, group=_group)
        ambari_config['protocol'] = self.config.get('protocol')
        ambari_config['port'] = self.config.get('port')
        ambari_config['username'] = self.config.get('username')
        ambari_config['password'] = self.config.get('password')
        ambari_config['validate_ssl'] = self.config.get('validate_ssl')
        ambari_config['cluster_name'] = _cluster_name

        self.inventory.set_variable(_hostname, 'ambari_config', ambari_config)

    def _populate_localhost(self):
        '''
            Add the localhost to the inventory file
        '''
        _group = 'local'
        _hostname = 'localhost'
        self.inventory.add_group(_group)
        self.inventory.add_host(_hostname, group=_group)
        self.inventory.set_variable(_hostname, 'ansible_host', '127.0.0.1')
        self.inventory.set_variable(_hostname, 'ansible_connection', 'local')
        self.inventory.set_variable(_hostname, 'ansible_become', 'false')

    ###########################################################################
    # Apache Ambari
    ###########################################################################

    def _initialize_client(self):
        '''
            Initialize Apache Ambari client
        '''

        # disable ssl warning
        if self.config.get('validate_ssl') == False:
            urllib3.disable_warnings()

        # initiate Apache Ambari client
        self._client = Ambari(self.config.get('hostname'),
                              port=int(self.config.get('port')),
                              username=self.config.get('username'),
                              password=self.config.get('password'),
                              protocol=self.config.get('protocol'),
                              validate_ssl=self.config.get('validate_ssl'))

    def _get_cluster_name(self):
        '''
            :return name of the cluster
        '''
        for cluster in self._client.clusters:
            return cluster.cluster_name

    def _get_services_name(self, cluster_name):
        '''
            :param cluster_name: name of the cluster
            :return names of the services installed on the cluster
        '''
        services_name = []
        for service in self._client.clusters(cluster_name).services:
            for component in service.components:
                services_name.append(component.service_name)
        return sorted(set(services_name))

    def _get_components_name(self, cluster_name, service_name):
        '''
            :param cluster_name: name of the cluster
            :param service_name: name of the service
            :return names of the components installed on the cluster
        '''
        components_name = []
        for component in self._client.clusters(cluster_name).services(service_name).components:
            components_name.append(component.component_name)
        return sorted(set(components_name))

    def _get_hosts_name(self, cluster_name):
        '''
            :param cluster_name: name of the cluster
            :return name of the healthy nodes on the cluster
        '''
        hosts_name = []
        for host in self._client.clusters(cluster_name).hosts:
            hosts_name.append(host.host_name)
        return sorted(set(hosts_name))

    def _get_host(self, host_name):
        '''
            :param host_name: name of the host
            :return host
        '''
        return self._client.hosts(host_name)

    def _get_host_components(self, cluster_name, host_name):
        '''
            :param cluster_name: name of the cluster
            :param host_name: name of the host
            :return components installed on the host
        '''
        return self._client.clusters(cluster_name).hosts(host_name).components

    def _get_service_current_configuration(self, cluster_name, service_name):
        '''
            :param cluster_name: name of the cluster
            :param service_name: name of the service
        '''
        protocol = 'http'
        if self.config.get('protocol'):
            if self.config.get('protocol') == 'https':
                protocol = self.config.get('protocol')

        url = protocol + '://' + self.config.get('hostname') + ':' + str(self.config.get('port')) + '/api/v1/clusters/' + \
            cluster_name + \
            '/configurations/service_config_versions?service_name.in(' + \
            service_name + ')&is_current=true'
        headers = {'X-Requested-By': 'ambari'}
        response = requests.get(url, headers=headers, auth=HTTPBasicAuth(
            self.config.get('username'), self.config.get('password')), verify=False)

        if response.ok:
            return response.json()
        else:
            response.raise_for_status()
