#!/usr/bin/python

DOCUMENTATION = '''
---
module: azure_ip_address
short_description: create or delete a reserved ip address
description:
     - Creates or deletes reserved IP addresses. This module has a dependency on python-azure >= 0.7.1
version_added: "1.9"
options:
  name:
    description:
      - name of the reserved IP address
    required: true
    default: null
  label:
    description:
      - a label for the reserved IP address (up to 100 characters)
    required: false
    default: null
  location:
    description:
      - the azure location to use (e.g. 'East US')
    required: true
    default: null
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
    default: "no"
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
      - create or delete the reserved IP address
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
    module: azure_ip_address
    name: my-ip-address
    location: 'East US'
    wait: yes

# Delete reserved IP address
- local_action:
    module: azure_ip_address
    name: my-ip_address
    state: absent
'''

import base64
import datetime
import os
import sys
import time
from urlparse import urlparse

AZURE_LOCATIONS = ['South Central US',
                   'Central US',
                   'East US 2',
                   'East US',
                   'West US',
                   'North Central US',
                   'North Europe',
                   'West Europe',
                   'East Asia',
                   'Southeast Asia',
                   'Japan West',
                   'Japan East',
                   'Brazil South']

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

def create_ip_address(module, azure):
    """
    Create new reserved IP address

    module : AnsibleModule object
    azure: authenticated azure ServiceManagementService object

    Returns:
        True if a new servce was created, false otherwise
    """
    name = module.params.get('name')
    label = module.params.get('label')
    location = module.params.get('location')
    wait = module.boolean(module.params.get('wait'))
    wait_timeout = int(module.params.get('wait_timeout'))

    # Check if a deployment with the same name already exists
    reserved_ip_address = None
    try:
        reserved_ip_address = azure.get_reserved_ip_address(name=name)
    except WindowsAzureMissingResourceError as e:
        pass  # no such reserved ip address
    except WindowsAzureError as e:
        module.fail_json(msg="failed to find the reserved IP address, error was: %s" % str(e))

    if reserved_ip_address:
        changed = False
    else:
        changed = True
        # Create reserved IP address if necessary
        try:
            result = azure.create_reserved_ip_address(name=name, label=label, location=location)
            if wait:
                _wait_for_completion(azure, result, wait_timeout, "create_reserved_ip_address")
                reserved_ip_address = azure.get_reserved_ip_address(name=name)
        except WindowsAzureError as e:
            module.fail_json(msg="failed to create the new reserved IP address: %s" % str(e))

    return (changed, reserved_ip_address)

#    try:
#        service = azure.get_hosted_service_properties(service_name=name)
#        return (changed, service)
#    except WindowsAzureError as e:
#        module.fail_json(msg="failed to lookup the deployment information for %s, error was: %s" % (name, str(e)))

def delete_ip_address(module, azure):
    """
    Deletes a reserved IP address

    module : AnsibleModule object
    azure: authenticated azure ServiceManagementService object

    Returns:
        True if a reserved IP address was deleted, false otherwise
    """

    name = module.params.get('name')
    wait = module.params.get('wait')
    wait_timeout = int(module.params.get('wait_timeout'))

    changed = False

    reserved_ip_address = None
    try:
        reserved_ip_address = azure.get_reserved_ip_address(name=name)
    except WindowsAzureMissingResourceError as e:
        pass  # no such reserved ip address
    except WindowsAzureError as e:
        module.fail_json(msg="failed to find the reserved IP address, error was: %s" % str(e))

    # Delete service
    if reserved_ip_address:
        changed = True
        try:
            result = azure.delete_reserved_ip_address(name=name)
            if (wait):
                _wait_for_completion(azure, result, wait_timeout, "delete_reserved_ip_address")
        except WindowsAzureError as e:
            module.fail_json(msg="failed to delete the reserved IP address %s, error was: %s" % (name, str(e)))

    return changed, reserved_ip_address

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
            name=dict(),
            label=dict(),
            location=dict(choices=AZURE_LOCATIONS),
            subscription_id=dict(no_log=True),
            management_cert_path=dict(),
            state=dict(default='present', choices=['present', 'absent']),
            wait=dict(type='bool', default=False),
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
        (changed, reserved_ip_address) = delete_ip_address(module, azure)

    elif module.params.get('state') == 'present':
        # Changed is always set to true when provisioning new instances
        if not module.params.get('name'):
            module.fail_json(msg='name parameter is required for new reserved IP address')
        if not module.params.get('location'):
            module.fail_json(msg='location parameter is required for new reserved IP address')
        (changed, reserved_ip_address) = create_ip_address(module, azure)

    module.exit_json(changed=changed, reserved_ip_address=json.loads(json.dumps(reserved_ip_address, default=lambda o: o.__dict__)))


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
