#!/usr/bin/python

DOCUMENTATION = '''
---
module: azure_affinity_group
short_description: create or delete an affinity group
description:
     - Creates or deletes affinity groups. This module has a dependency on python-azure >= 0.7.1
version_added: "1.9"
options:
  name:
    description:
      - name of the affinity group
    required: true
    default: null
  location:
    description:
      - the azure location to use (e.g. 'East US')
    required: true
    default: null
  label:
    description:
      - a label for the data disk (up to 100 characters)
    required: false
    default: null
  description:
    description:
      - a description for the affinity group
    required: false
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
      - create or delete the affinity group
    required: false
    default: 'present'
    aliases: []

requirements: [ "azure" ]
author: Darren Warner
'''

EXAMPLES = '''
# Note: None of these examples set subscription_id or management_cert_path
# It is assumed that their matching environment variables are set.

# Create an affinity group
- local_action:
    module: azure_affinity_group
    name: my-affinity-group
    location: 'East US'

# Delete an affinity group
- local_action:
    module: azure_affinity_group
    name: my-affinity-group
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
        elif operation_result.status == "InProgress":
            continue
        else:
            raise WindowsAzureError('Failed to wait for async operation ' + msg + ': [' + operation_result.error.code + '] ' + operation_result.error.message)

    raise WindowsAzureError('Timed out waiting for async operation ' + msg + ' "' + str(promise.request_id) + '" to complete.')

def create_affinity_group(module, azure):
    """
    Create new affinity group

    module : AnsibleModule object
    azure: authenticated azure ServiceManagementService object

    Returns:
        True if a new servce was created, false otherwise
    """
    name = module.params.get('name')
    label = module.params.get('label')
    location = module.params.get('location')
    description = module.params.get('description')
    wait = module.boolean(module.params.get('wait'))
    wait_timeout = int(module.params.get('wait_timeout'))

    # Check if the affinity group already exists
    affinity_group = None
    try:
        affinity_group = azure.get_affinity_group_properties(affinity_group_name=name)
    except WindowsAzureMissingResourceError as e:
        pass  # no such service
    except WindowsAzureError as e:
        module.fail_json(msg="failed to find the affinity group '%s': %s" % (name, str(e)))

    # See if the affinity group needs to be changed
    update = False
    if affinity_group:
        if affinity_group.description != description:
            update = True
        if affinity_group.label != label:
            update = True
        if affinity_group.location != location:
            module.fail_json(msg="cannot change the location of an existing affinity group")

    # Create/change the affinity group
    if affinity_group and not update:
        changed = False
    elif update:
        changed = True
        try:
            result = azure.update_affinity_group(affinity_group_name=name, label=label, description=description)
            if (wait):
                _wait_for_completion(azure, result, wait_timeout, "create_affinity_group")
        except WindowsAzureError as e:
            module.fail_json(msg="failed to create the new affinity group: %s" % str(e))
    else:
        changed = True
        try:
            result = azure.create_affinity_group(name=name, label=label, location=location, description=description)
            if (wait):
                _wait_for_completion(azure, result, wait_timeout, "create_affinity_group")
        except WindowsAzureError as e:
            module.fail_json(msg="failed to create the new affinity group: %s" % str(e))

    # Get the affinity group properties
    if changed:
        try:
            affinity_group = azure.get_affinity_group_properties(affinity_group_name=name)
        except WindowsAzureError as e:
            module.fail_json(msg="failed to lookup the affinity group '%s': %s" % (name, str(e)))

    return (changed, affinity_group)

def delete_affinity_group(module, azure):
    """
    Deletes an affinity group

    module : AnsibleModule object
    azure: authenticated azure ServiceManagementService object

    Returns:
        True if an affinity group was deleted, false otherwise
    """

    name = module.params.get('name')
    wait = module.params.get('wait')
    wait_timeout = int(module.params.get('wait_timeout'))

    changed = False

    affinity_group = None
    try:
        affinity_group = azure.get_affinity_group_properties(affinity_group_name=name)
    except WindowsAzureMissingResourceError as e:
        pass  # no such service
    except WindowsAzureError as e:
        module.fail_json(msg="failed to find the affinity group '%s': %s" % (name, str(e)))

    # Delete affinity group
    if affinity_group:
        changed = True
        try:
            result = azure.delete_affinity_group(affinity_group_name=name)
            if (wait):
                _wait_for_completion(azure, result, wait_timeout, "delete_affinity_group")
        except WindowsAzureError as e:
            module.fail_json(msg="failed to delete the affinity group '%s': %s" % (name, str(e)))

    return changed, affinity_group

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
            name=dict(required=True),
            label=dict(),
            location=dict(choices=AZURE_LOCATIONS),
            description=dict(),
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
        (changed, affinity_group) = delete_affinity_group(module, azure)

    elif module.params.get('state') == 'present':
        # Changed is always set to true when provisioning new instances
        if not module.params.get('location'):
            module.fail_json(msg='locationis required for new affinity group')
        (changed, affinity_group) = create_affinity_group(module, azure)

    module.exit_json(changed=changed, affinity_group=json.loads(json.dumps(affinity_group, default=lambda o: o.__dict__)))


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
