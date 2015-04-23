ansible-module-azure
====================

This repo contains an Azure module for Ansible. The core Ansible Azure module (from ansible-modules-core) was taken as the basis for this expanded set of functionality.

Supported Azure resources include:
* Management Certificates (azure_management_certificate)
* Reserved IP addresses (azure_reserved_ip_address)
* Cloud Services (azure_service)
* Storage Accounts (azure_storage_account)
* Storage Account Keys (azure_storage_account_keys)
* Storage Containers (azure_storage_container)
* Virtual Machines (azure_vm)

Take care to submit tickets to the appropriate repo where modules are contained.  The docs.ansible.com website indicates this at the bottom of each module documentation page.

Reporting bugs
==============

Take care to submit tickets to the appropriate repo where modules are contained. The repo is mentioned at the bottom of module documentation page at [docs.ansible.com](http://docs.ansible.com/).

Testing modules
===============

Ansible [module development guide](http://docs.ansible.com/developing_modules.html#testing-modules) contains the latest info about that.

License
=======

As with Ansible, modules distributed with Ansible are GPLv3 licensed.

Installation
============

Clone this repo into the directory where your inventory file resides and start using!
