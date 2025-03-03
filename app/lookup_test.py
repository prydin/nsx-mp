import requests
from aria.ops.object import Identifier
from aria.ops.suite_api_client import SuiteApiClient, SuiteApiConnectionParameters

from app.ops_helper import lookup_resource


def check_result(result):
    if result.status_code > 299 or result.status_code < 200:
        raise Exception(f"{result.status_code}: {result.text}")

payload = {
    "username": "admin",
    "password": "VMware123!",
    "authSource": "LOCAL"
}

ops_url = "https://10.60.0.160/suite-api/api"
headers = { "Accept": "application/json", "Content-Type": "application/json"}

connection_params = SuiteApiConnectionParameters("10.60.0.160", "admin", "VMware123!", "LOCAL")
client = SuiteApiClient(connection_params)
client.get_token()
key = "edge1-mgmt"
ADAPTER_KIND_KEY = "NSXTAdapter"
RESOURCE_KIND_KEY = "TransportNode"

identifiers = [Identifier("ID", "83c5f16c-b57e-4c2b-afb2-7642fb2c749f", True)]

query = {
    "name": [key],
    "adapterKind": [ADAPTER_KIND_KEY],
    "resourceKind": [RESOURCE_KIND_KEY],
#    "propertyName": "MANAGEMENT_CLUSTER_UUID",
#    "propertyValue": "c1a9c4fd-d3a1-4f7e-aeb7-ec47086806ba"
}

result = lookup_resource(client, query, identifiers)
print(result)


"""
result = requests.post(ops_url + "/auth/token/acquire", json=payload, verify=False, headers=headers)
check_result(result)
token = result.json()["token"]
headers["Authorization"] = "OpsToken " + token

key = "edge1-mgmt"
ADAPTER_KIND_KEY = "NSXTAdapter"
RESOURCE_KIND_KEY = "TransportNode"

payload = {
    "name": [key],
    "adapterKind": [ADAPTER_KIND_KEY],
    "resourceKind": [RESOURCE_KIND_KEY],
#    "propertyName": "MANAGEMENT_CLUSTER_UUID",
#    "propertyValue": "c1a9c4fd-d3a1-4f7e-aeb7-ec47086806ba"
}

# Find or create resource corresponding to subject
result = requests.post(ops_url + "/resources/query", json=payload, verify=False, headers=headers)
resources = result.json()
print(result.content)
resource = result.json()["resourceList"][0]
"""