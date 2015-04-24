#!/usr/bin/python

DOCUMENTATION = '''
---
module: azure_storage_account_keys
short_description: create or delete a storage account in azure
description:
     - Creates or deletes storage accounts. This module has a dependency on python-azure >= 0.7.1
version_added: "1.9"
options:
  name:
    description:
      - name of the storage account
    required: true
    default: null
  key_type:
    description:
      - which key to regenerate
    required: true
    default: Primary
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
      - regenerate key or do nothing (useful for obtaining the current key values)
    required: false
    default: 'regenerate'
    aliases: []

requirements: [ "azure" ]
author: Darren Warner
'''

EXAMPLES = '''
# Note: None of these examples set subscription_id or management_cert_path
# It is assumed that their matching environment variables are set.

# Regenerate the primary account key
- local_action:
    module: azure_storage_account_keys
    name: my-storage-account

# Get the current storage account keys
- local_action:
    module: azure_storage_account_keys
    name: my-storage-account
    state: nothing
'''

import base64
import datetime
import os
import sys
import time
from urlparse import urlparse

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

def regenerate_storage_account_key(module, azure):
    """
    Regenerate a storage account key

    module : AnsibleModule object
    azure: authenticated azure ServiceManagementService object

    Returns:
        True if a new servce was created, false otherwise
    """
    name = module.params.get('name')
    key_type = module.params.get('key_type')
    wait = module.params.get('wait')
    wait_timeout = int(module.params.get('wait_timeout'))

    changed = True
    try:
        storage_service = azure.regenerate_storage_account_keys(service_name=name, key_type=key_type)
    except WindowsAzureError as e:
        module.fail_json(msg="failed to regenerate storage account keys: %s" % str(e))

    return (changed, storage_service.storage_service_keys)

def get_storage_account_keys(module, azure):
    """
    Gets account keys associated with a storage account

    module : AnsibleModule object
    azure: authenticated azure ServiceManagementService object

    Returns:
        Always False
    """

    name = module.params.get('name')
    key_type = module.params.get('key_type')

    changed = False

    storage_account = None
    try:
        storage_account_keys = azure.get_storage_account_keys(service_name=name)
    except WindowsAzureMissingResourceError as e:
        pass  # no such service
    except WindowsAzureError as e:
        module.fail_json(msg="failed to find the storage account keys, error was: %s" % str(e))

    return changed, storage_account_keys.storage_service_keys

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
            key_type=dict(default='Primary', choices=['Primary', 'Secondary']),
            subscription_id=dict(no_log=True),
            management_cert_path=dict(),
            state=dict(default='regenerate', choices=['regenerate', 'nothing']),
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

    if module.params.get('state') == 'nothing':
        (changed, storage_account_keys) = get_storage_account_keys(module, azure)

    elif module.params.get('state') == 'regenerate':
        # Changed is always set to true when provisioning new instances
        if not module.params.get('name'):
            module.fail_json(msg='name parameter is required for new storage account')
        (changed, storage_account_keys) = regenerate_storage_account_key(module, azure)

    module.exit_json(changed=changed, storage_account_keys=json.loads(json.dumps(storage_account_keys, default=lambda o: o.__dict__)))


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
