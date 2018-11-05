# ambari - Apache Ambari inventory source

## Synopsis

* Get inventory hosts from [Apache Ambari](https://ambari.apache.org/)
* Uses a YAML configuration file that ends with ambari.(yml|yaml)

### Requirements

This below requirements are needed on the local node that executes this plugin.

* Ansible > 2.7.0
* sudo pip3 install [python-ambariclient](https://github.com/jimbobhickville/python-ambariclient)

## Parameters

    plugin: ambari
    hostname: ambari-server.makayel.local
    port: 8443
    username: localuser
    password: localpass
    protocol: https
    validate_ssl: False
    ansible_user: nodesuser
    ansible_ssh_pass: nodespass

## Tests

    ansible-inventory -i inventory/env.ambari.yml --list
    ansible -i inventory/env.ambari.yml all -m ping

## Status
### Author
    Michael Hatoum <michael@adaltas.com>
