#!/usr/bin/python

DOCUMENTATION = '''
---
module: azure_blob_lease
short_description: acquires or releases a lease on a blob
description:
     - Acquires, renews, releases, or breaks leases on individual blobs. This module has a dependency on python-azure >= 0.7.1
version_added: "1.9"
options:
  name:
    description:
      - name of the blob
    required: true
    default: null
  container:
    description:
      - name of the container
    required: true
    default: null
  lease_id:
    description:
      - guid of an existing lease (to renew a lease or release without breaking)
    required: false
    default: null
  duration_s:
    description:
      - length of time to obtain the lease for (-1 is never expire)
    required: false
    default: null
  break:
    description:
      - breaks a lease (if state is released)
    required: false
    default: false
  break_duration:
    description:
      - period after a lease is broken to wait before a new lease can be obtained
    required: false
    default: null
  account_name:
    description:
      - name of the storage account
    required: true
    default: null
  account_key:
    description:
      - key used to access the storage account (either primary or secondary)
    required: true
    default: null
  state:
    description:
      - sets the lease to acquired (or renewed) or released (or broken)
    required: true
    default: 'acquired'
    aliases: []

requirements: [ "azure" ]
author: Darren Warner
'''

EXAMPLES = '''
# Note: None of these examples set account name or account key

# Acquire a lease on a blob
- local_action:
    module: azure_blob_lease
    name: my-blob.vhd
    container: vhds
    account_name: my-storage-account
    account_key: my-storage-account-key

# Breaks a lease on a blob immediately
- local_action:
    module: azure_blob_lease
    name: my-blob.vhd
    container: vhds
    account_name: my-storage-account
    account_key: my-storage-account-key
    break: yes
    break_period: 0
    state: released
'''

import sys
import json

try:
    import azure as windows_azure

    from azure import WindowsAzureError, WindowsAzureMissingResourceError
    from azure.storage import (CloudStorageAccount)
except ImportError as a:
    print "failed=True msg='azure required for this module': %s" % (a)
    sys.exit(1)

def aquire_blob_lease(module, azure):
    """
    Aquire a lease on a container

    module : AnsibleModule object
    azure: authenticated azure BlobService object

    Returns:
        True if a new blob lease is acquired, false otherwise
    """
    name = module.params.get('name')
    container = module.params.get('container')
    duration = int(module.params.get('duration_s'))
    lease_id = module.params.get('lease_id')

    try:
        blob_properties = azure.get_blob_properties(container_name=container, blob_name=name, x_ms_lease_id=lease_id)
    except WindowsAzureError as e:
        module.fail_json(msg="failed to get blob properties: %s" % str(e))

    changed = False

    changed = not lease_id
    try:
        lease = azure.lease_blob(container_name=container, blob_name=name, x_ms_lease_action='acquire' if not lease_id else 'renew', x_ms_lease_duration=duration, x_ms_lease_id=lease_id)
    except WindowsAzureError as e:
        module.fail_json(msg="failed to lease blob: %s" % str(e))

    return (changed, lease)

def release_blob_lease(module, azure):
    """
    Releases a lease on a blob

    module : AnsibleModule object
    azure: authenticated azure BlobService object

    Returns:
        True if a lease was released
    """

    name = module.params.get('name')
    container = module.params.get('container')
    lease_id = module.params.get('lease_id')
    break_period = module.params.get('break_period')
    break_lease = module.boolean(module.params.get('break'))

    try:
        blob_properties = azure.get_blob_properties(container_name=container, blob_name=name)
    except WindowsAzureError as e:
        module.fail_json(msg="failed to get blob properties: %s" % str(e))

    changed = False
    if blob_properties['x-ms-lease-state'] == 'available':
        return (changed, None)

    changed = True

    result = None
    try:
        result = azure.lease_blob(container_name=container, blob_name=name, x_ms_lease_action='release' if not break_lease else 'break', x_ms_lease_id=lease_id, x_ms_lease_break_period=break_period)
    except WindowsAzureMissingResourceError as e:
        print e
    except WindowsAzureError as e:
        module.fail_json(msg="failed to find the storage container: %s" % str(e))

    return (changed, result)

def main():
    module = AnsibleModule(
        argument_spec=dict(
            name=dict(required=True),
            container=dict(required=True),
            lease_id=dict(),
            duration_s=dict(type='int'),
            break_lease=dict(type='bool', default=False, aliases=[ 'break' ]),
            break_period=dict(),
            proposed_lease=dict(),
            account_name=dict(required=True),
            account_key=dict(required=True),
            state=dict(default='acquired', choices=['acquired', 'released'])
        )
    )

    account_name = module.params.get('account_name')
    account_key = module.params.get('account_key')

    azure = CloudStorageAccount(account_name, account_key).create_blob_service()

    if module.params.get('state') == 'released':
        (changed, lease) = release_blob_lease(module, azure)

    elif module.params.get('state') == 'acquired':
        if not module.params.get('duration_s'):
            module.fail_json(msg='duration_s parameter is required for lease aquisition')
        (changed, lease) = aquire_blob_lease(module, azure)

    module.exit_json(changed=changed, lease=json.loads(json.dumps(lease, default=lambda o: o.__dict__)))


# import module snippets
from ansible.module_utils.basic import *

main()
