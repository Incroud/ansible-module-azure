#!/usr/bin/python

DOCUMENTATION = '''
---
module: azure_management_certificate
short_description: creates a certificate from a publish settings file
description:
     - Creates a PEM certificate from a downloaded .publishsettings file. This module has a dependency on python-azure >= 0.7.1
version_added: "1.9"
options:
  publish_settings_path:
    description:
      - filename of the .publishsettings file
    required: true
    default: null
  management_cert_path:
    description:
      - path to where the management certificate file will be written. Overrides the AZURE_CERT_PATH environment variable
    required: false
    default: null
  subscription_id:
    description:
      - azure subscription id. Overrides the AZURE_SUBSCRIPTION_ID environment variable
    required: false
    default: null
  state:
    description:
      - create or delete the management certificate
    required: false
    default: 'present'
    aliases: []

requirements: [ "azure" ]
author: Darren Warner
'''

EXAMPLES = '''
# Note: None of these examples set subscription_id or management_cert_path
# It is assumed that their matching environment variables are set.

# Export a management certificate from a .publishsettings file
- local_action:
    module: azure_management_certificate
    publish_settings_path: /etc/azure/credentials.publishsettings
    management_cert_path: /etc/azure/management.pem

# Delete a management certificate
- local_action:
    module: azure_management_certificate
    management_cert_path: /etc/azure/management.pem
    state: absent
'''

import base64
import datetime
import os
import sys
import time
import hashlib
from urlparse import urlparse

try:
    import azure.servicemanagement

except ImportError as a:
    print "failed=True msg='azure required for this module': %s" % (a)
    sys.exit(1)

from distutils.version import LooseVersion
from types import MethodType
import json

def create_management_certificate(module):
    """
    Export a management certificate from a publishsettings file

    module : AnsibleModule object
    azure: authenticated azure ServiceManagementService object

    Returns:
        True if a new management certificate was created, false otherwise
    """
    publish_settings_path = module.params.get('publish_settings_path')
    management_cert_path = module.params.get('management_cert_path')
    subscription_id = module.params.get('subscription_id')

    # Check if the management cert already exists
    certificate_md5 = None
    if os.path.isfile(management_cert_path):
        certificate_md5 = hashlib.md5(open(management_cert_path, 'r').read()).digest()

    try:
        certificate = azure.servicemanagement.get_certificate_from_publish_settings(publish_settings_path=publish_settings_path, path_to_write_certificate=management_cert_path, subscription_id=subscription_id)
    except Exception as e:
        module.fail_json(msg="failed to get management certificate: %s" % str(e))

    new_certificate_md5 = hashlib.md5(open(management_cert_path, 'r').read()).digest()

    changed = new_certificate_md5 != certificate_md5

    return (changed, certificate)

def delete_management_certificate(module):
    """
    Deletes a management certificate

    module : AnsibleModule object
    azure: authenticated azure ServiceManagementService object

    Returns:
        True if a management certificate was deleted
    """

    management_cert_path = module.params.get('management_cert_path')
    subscription_id = module.params.get('subscription_id')

    if not os.path.isfile(management_cert_path):
        return (False, subscription_id)

    try:
        os.remove(management_cert_path)
    except OSError as e:
        module.fail_json(msg="failed to delete management certificate: %s" % str(e))

    return (True, subscription_id)

def get_azure_creds(module):
    # Check modul args for credentials, then check environment vars
    subscription_id = module.params.get('subscription_id')
    if not subscription_id:
        subscription_id = os.environ.get('AZURE_SUBSCRIPTION_ID', None)

    management_cert_path = module.params.get('management_cert_path')
    if not management_cert_path:
        management_cert_path = os.environ.get('AZURE_CERT_PATH', None)
    if not management_cert_path:
        module.fail_json(msg="No management_cert_path provided. Please set 'AZURE_CERT_PATH' or use the 'management_cert_path' parameter")

    return subscription_id, management_cert_path

def main():
    module = AnsibleModule(
        argument_spec=dict(
            publish_settings_path=dict(),
            management_cert_path=dict(),
            subscription_id=dict(),
            state=dict(default='present', choices=['present', 'absent']),
        )
    )
    # create azure ServiceManagementService object
    subscription_id, management_cert_path = get_azure_creds(module)

    if module.params.get('state') == 'absent':
        (changed, subscription_id) = delete_management_certificate(module)

    elif module.params.get('state') == 'present':
        if not module.params.get('publish_settings_path'):
            module.fail_json(msg='publish_settings_path parameter is required for exporting a management certificate')
        (changed, subscription_id) = create_management_certificate(module)

    module.exit_json(changed=changed, subscription_id=subscription_id)

# import module snippets
from ansible.module_utils.basic import *

main()
