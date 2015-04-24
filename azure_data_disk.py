#!/usr/bin/python

DOCUMENTATION = '''
---
module: azure_data_disk
short_description: create or terminate a data disk in azure
description:
     - Creates or deletes data disks. This module has a dependency on python-azure >= 0.7.1
version_added: "1.9"
options:
  service:
    description:
      - name of the service
    required: true
    default: null
  deployment:
    description:
      - name of the deployment
    required: true
    default: null
  role_name:
    description:
      - name of the role
    required: false
    default: null
  lun:
    description:
      - the logic unit number (valid values are between 0 and 15)
    required: false
    default: null
  host_caching:
    description:
      - the platform caching behavior for read/write efficiency
    required: true
    default: ReadOnly
  media_link:
    description:
      - the location where the media for the disk is located
    required: false
    default: null
  source_media_link:
    description:
      - the location which is mounted when the virtual machine is created
    required: false
    default: ReadOnly
  label:
    description:
      - a label for the data disk (up to 100 characters)
    required: true
    default: null
  size_gb:
    description:
      - the size of the disk (in Gb)
    required: true
    default: null
  delete_vhd:
    description:
      - deletes the underlying VHD blob
    required: false
    default: false
  subscription_id:
    description:
      - azure subscription id. Overrides the AZURE_SUBSCRIPTION_ID environement variable.
    required: false
    default: null
  management_cert_path:
    description:
      - path to an azure management certificate associated with the subscription id. Overrides the AZURE_CERT_PATH environement variable.
    required: false
    default: null
  wait:
    description:
      - wait for the service to be created before returning
    required: false
    default: "yes"
    choices: [ "yes", "no" ]
    aliases: []
  wait_timeout:
    description:
      - how long before wait gives up, in seconds
    default: 600
    aliases: []
  wait_timeout_redirects:
    description:
      - how long before wait gives up for redirects, in seconds
    default: 300
    aliases: []
  state:
    description:
      - create or delete the data disk
    required: false
    default: 'present'
    aliases: []

requirements: [ "azure" ]
author: Darren Warner
'''

EXAMPLES = '''
# Note: None of these examples set subscription_id or management_cert_path
# It is assumed that their matching environment variables are set.

# Provision virtual machine example
- local_action:
    module: azure_data_disk
    name: my-data-disk
    location: 'East US'
    wait: yes

# Terminate virtual machine example
- local_action:
    module: azure_data_disk
    name: my-data-disk
    state: absent
'''

import base64
import datetime
import os
import sys
import time
from urlparse import urlparse

AZURE_HOST_CACHING = ['None',
                      'ReadOnly',
                      'ReadWrite']

try:
    import azure as windows_azure

    from azure import WindowsAzureError, WindowsAzureMissingResourceError
    from azure.servicemanagement import (ServiceManagementService, SSH, PublicKeys,
                                         PublicKey)
except ImportError as a:
    print "failed=True msg='azure required for this module': %s" % (a)
    sys.exit(1)

from distutils.version import LooseVersion
from types import MethodType
import json

def _wait_for_completion(azure, promise, wait_timeout, msg):
    if not promise: return
    wait_timeout = time.time() + wait_timeout
    while wait_timeout > time.time():
        operation_result = azure.get_operation_status(promise.request_id)
        time.sleep(5)
        if operation_result.status == "Succeeded":
            return

    raise WindowsAzureError('Timed out waiting for async operation ' + msg + ' "' + str(promise.request_id) + '" to complete.')

def create_data_disk(module, azure):
    """
    Create new data disk

    module : AnsibleModule object
    azure: authenticated azure ServiceManagementService object

    Returns:
        True if a new servce was created, false otherwise
    """
    service = module.params.get('service')
    deployment = module.params.get('deployment')
    role = module.params.get('role')
    lun = module.params.get('lun')
    host_caching = module.params.get('host_caching')
    media_link = module.params.get('media_link')
    label = module.params.get('label')
    name = module.params.get('name')
    size_gb = int(module.params.get('size_gb'))
    source_media_link = module.params.get('source_media_link')
    wait = module.boolean(module.params.get('wait'))
    wait_timeout = int(module.params.get('wait_timeout'))

    # Check if a data disk is already attached to the deployment
    data_disk = None
    try:
        data_disk = azure.get_data_disk(service_name=service, deployment_name=deployment, role_name=role, lun=lun)
    except WindowsAzureMissingResourceError as e:
        pass  # no such service
    except WindowsAzureError as e:
        module.fail_json(msg="failed to find the data disk, error was: %s" % str(e))

    if data_disk:
        changed = False
    else:
        changed = True
        # Create the data disk if necessary
        try:
            result = azure.add_data_disk(service_name=service, deployment_name=deployment, role_name=role, lun=lun, host_caching=host_caching, media_link=media_link, disk_label=label, disk_name=name, logical_disk_size_in_gb=size_gb, source_media_link=source_media_link)
            if (wait):
                _wait_for_completion(azure, result, wait_timeout, "add_data_disk")
        except WindowsAzureError as e:
            module.fail_json(msg="failed to add a data disk: %s" % str(e))

    try:
        data_disk = None
        if (wait):
            data_disk = azure.get_data_disk(service_name=service, deployment_name=deployment, role_name=role, lun=lun)
        return (changed, data_disk)
    except WindowsAzureError as e:
        module.fail_json(msg="failed to lookup the data disk information for %s, error was: %s" % (name, str(e)))

def delete_data_disk(module, azure):
    """
    Deletes a data disk

    module : AnsibleModule object
    azure: authenticated azure ServiceManagementService object

    Not yet supported: handle deletion of attached data disks.

    Returns:
        True if a service was deleted, false otherwise
    """

    service = module.params.get('name')
    deployment = module.params.get('name')
    role = module.params.get('name')
    lun = module.params.get('name')
    delete_vhd = module.boolean(module.params.get('delete_vhd'))
    wait = module.params.get('wait')
    wait_timeout = int(module.params.get('wait_timeout'))

    changed = False

    data_disk = None
    try:
        data_disk = azure.get_data_disk(service_name=service, deployment_name=deployment, role_name=role, lun=lun)
    except WindowsAzureMissingResourceError as e:
        pass  # no such service
    except WindowsAzureError as e:
        module.fail_json(msg="failed to find the data disk, error was: %s" % str(e))

    # Delete data disk
    if data_disk:
        changed = True
        try:
            result = azure.delete_data_disk(service_name=service, deployment_name=deployment, role_name=role, lun=lun, delete_vhd=delete_vhd)
            if (wait):
                _wait_for_completion(azure, result, wait_timeout, "delete_data_disk")
        except WindowsAzureError as e:
            module.fail_json(msg="failed to delete the data disk %s, error was: %s" % (name, str(e)))

    return changed, data_disk

def get_azure_creds(module):
    # Check modul args for credentials, then check environment vars
    subscription_id = module.params.get('subscription_id')
    if not subscription_id:
        subscription_id = os.environ.get('AZURE_SUBSCRIPTION_ID', None)
    if not subscription_id:
        module.fail_json(msg="No subscription_id provided. Please set 'AZURE_SUBSCRIPTION_ID' or use the 'subscription_id' parameter")

    management_cert_path = module.params.get('management_cert_path')
    if not management_cert_path:
        management_cert_path = os.environ.get('AZURE_CERT_PATH', None)
    if not management_cert_path:
        module.fail_json(msg="No management_cert_path provided. Please set 'AZURE_CERT_PATH' or use the 'management_cert_path' parameter")

    return subscription_id, management_cert_path

def main():
    module = AnsibleModule(
        argument_spec=dict(
            service=dict(),
            deployment=dict(),
            role=dict(),
            lun=dict(),
            host_caching=dict(choices=AZURE_HOST_CACHING, default='ReadOnly'),
            media_link=dict(),
            label=dict(),
            name=dict(),
            size_gb=dict(),
            source_media_link=dict(),
            subscription_id=dict(no_log=True),
            management_cert_path=dict(),
            state=dict(default='present', choices=['present', 'absent']),
            wait=dict(type='bool', default=True),
            wait_timeout=dict(default=600),
            wait_timeout_redirects=dict(default=300)
        )
    )
    # create azure ServiceManagementService object
    subscription_id, management_cert_path = get_azure_creds(module)

    wait_timeout_redirects = int(module.params.get('wait_timeout_redirects'))
    if LooseVersion(windows_azure.__version__) <= "0.8.0":
        # wrapper for handling redirects which the sdk <= 0.8.0 is not following
        azure = Wrapper(ServiceManagementService(subscription_id, management_cert_path), wait_timeout_redirects)
    else:
        azure = ServiceManagementService(subscription_id, management_cert_path)

    if module.params.get('state') == 'absent':
        (changed, data_disk) = delete_data_disk(module, azure)

    elif module.params.get('state') == 'present':
        # Changed is always set to true when provisioning new instances
        if not module.params.get('service'):
            module.fail_json(msg='service parameter is required for data disk')
        if not module.params.get('deployment'):
            module.fail_json(msg='deployment parameter is required for data disk')
        (changed, data_disk) = create_data_disk(module, azure)

    module.exit_json(changed=changed, data_disk=json.loads(json.dumps(data_disk, default=lambda o: o.__dict__)))


class Wrapper(object):
    def __init__(self, obj, wait_timeout):
        self.other = obj
        self.wait_timeout = wait_timeout

    def __getattr__(self, name):
        if hasattr(self.other, name):
            func = getattr(self.other, name)
            return lambda *args, **kwargs: self._wrap(func, args, kwargs)
        raise AttributeError(name)

    def _wrap(self, func, args, kwargs):
        if type(func) == MethodType:
            result = self._handle_temporary_redirects(lambda: func(*args, **kwargs))
        else:
            result = self._handle_temporary_redirects(lambda: func(self.other, *args, **kwargs))
        return result

    def _handle_temporary_redirects(self, f):
        wait_timeout = time.time() + self.wait_timeout
        while wait_timeout > time.time():
            try:
                return f()
            except WindowsAzureError as e:
                if not str(e).lower().find("temporary redirect") == -1:
                    time.sleep(5)
                    pass
                else:
                    raise e


# import module snippets
from ansible.module_utils.basic import *

main()
