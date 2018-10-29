# ambari - Apache Ambari inventory source

## Synopsis

* Get inventory hosts from [Apache Ambari](https://ambari.apache.org/)
* Uses a YAML configuration file that ends with ambari.(yml|yaml)

### Requirements

The below requirements are needed on the local master node that executes this inventory.

* sudo pip3 install [python-ambariclient](https://github.com/jimbobhickville/python-ambariclient)

## Parameters

    plugin: ambari
    host_name: ambari-server.makayel.local
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
