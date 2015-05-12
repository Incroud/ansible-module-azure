#!/usr/bin/python

DOCUMENTATION = '''
---
module: azure_blob_fetch
short_description: downloads a blob
description:
     - Fetches an object from blob storage. This module has a dependency on python-azure >= 0.7.1
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
  dest:
    description:
      - the full path name to where the object will be downloaded to
    required: true
    default: null
  overwrite:
    description:
      - download the blob, even if the destination file exists
    required: false
    default: false
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

requirements: [ "azure" ]
author: Darren Warner
'''

EXAMPLES = '''
# Fetch an object from blob storage
- local_action:
    module: azure_blob_fetch
    name: my-blob.bin
    container: blobs
    dest: /tmp/my-blob.bin
    account_name: my-storage-account
    account_key: my-storage-account-key
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

def get_blob(module, azure):
    """
    Download a blob

    module : AnsibleModule object
    azure: authenticated azure BlobService object

    Returns:
        True if an object was downloaded (and is different from any overwritten object)
    """
    name = module.params.get('name')
    container = module.params.get('container')
    snapshot = module.params.get('snapshot')
    lease_id = module.params.get('lease_id')
    dest = module.params.get('dest')
    overwrite = module.boolean(module.params.get('overwrite'))

    # Get the MD5 of any local file
    original_md5 = module.md5(dest)

    result = None
    if original_md5 and not overwrite:
        changed = False
    else:
        try:
            azure.get_blob_to_path(container_name=container, blob_name=name, file_path=dest, snapshot=snapshot, x_ms_lease_id=lease_id)
            changed = module.md5(dest) != original_md5
        except WindowsAzureError as e:
            module.fail_json(msg="failed to lease blob: %s" % str(e))

    return (changed)

def main():
    module = AnsibleModule(
        argument_spec=dict(
            name=dict(required=True),
            container=dict(required=True),
            snapshot=dict(),
            dest=dict(required=True),
            overwrite=dict(type='bool', default=False),
            lease_id=dict(),
            account_name=dict(required=True),
            account_key=dict(required=True),
            state=dict(default='acquired', choices=['acquired', 'released'])
        )
    )

    account_name = module.params.get('account_name')
    account_key = module.params.get('account_key')

    azure = CloudStorageAccount(account_name, account_key).create_blob_service()

    (changed) = get_blob(module, azure)

    module.exit_json(changed=changed)


# import module snippets
from ansible.module_utils.basic import *

main()
